"""Decision Lab stress test: per-supplier delay, suppliers switched off, demand change.

Everything is read-only. Only 'Create proposed orders' writes anything, and only proposals."""
import pytest
from fastapi.testclient import TestClient

from app import db
from app.inventory import Item
from app.lab import Unfilled, apply_stress, build_candidates, simulate, unfilled_details
from app.main import app
from app.policy import Policy
from app.suppliers import Supplier

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RESCUEBUY_DB", str(tmp_path / "test.db"))
    db.init_db(force=True)


@pytest.fixture(autouse=True)
def no_real_ai(monkeypatch):
    def broken_client(api_key=None):
        raise RuntimeError("AI disabled in tests")

    monkeypatch.setattr("app.ai.genai.Client", broken_client)
    monkeypatch.setattr("app.compare.choose_supplier", lambda opts: None)


def lab(**body):
    response = client.post("/lab/simulate", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def scenario(result, key):
    return next(s for s in result["scenarios"] if s["key"] == key)


def line(sc, item):
    return next(l for l in sc["bought"] if l["item"] == item)


# ---- Unit: the pure functions ----

POLICY = Policy(max_auto_spend=150, budget=1500)


def milk() -> Item:
    return Item("Milk", "Dairy", "l", stock=20, daily_usage=10, incoming=0, unit_cost=1.0, criticality=3)


def offers_for_milk() -> dict[str, list[Supplier]]:
    return {
        "Milk": [
            Supplier("Fast", 1.2, 1, min_order_qty=10, delivery_fee=5),
            Supplier("Slow", 0.5, 2, min_order_qty=10, delivery_fee=5),
        ]
    }


def test_apply_stress_with_no_inputs_changes_nothing():
    items, offers = [milk()], offers_for_milk()
    new_items, new_offers = apply_stress(items, offers)
    assert new_items[0].daily_usage == 10
    assert [s.name for s in new_offers["Milk"]] == ["Fast", "Slow"]


def test_apply_stress_scales_usage_and_drops_suppliers_without_touching_the_originals():
    items, offers = [milk()], offers_for_milk()
    new_items, new_offers = apply_stress(items, offers, demand_change_pct=30, unavailable=["Fast"])
    assert new_items[0].daily_usage == 13
    assert [s.name for s in new_offers["Milk"]] == ["Slow"]
    assert items[0].daily_usage == 10
    assert [s.name for s in offers["Milk"]] == ["Fast", "Slow"]


def test_unfilled_details_name_the_fastest_supplier_that_is_left():
    rows = unfilled_details([milk()], offers_for_milk(), ["Milk"])
    assert rows == [Unfilled("Milk", 2.0, "Fast", 1.0)]


def test_unfilled_item_with_no_supplier_at_all_has_no_fastest():
    rows = unfilled_details([milk()], {"Milk": []}, ["Milk"])
    assert rows == [Unfilled("Milk", 2.0, None, None)]


def test_simulate_without_stress_inputs_behaves_as_before():
    candidates, _ = build_candidates([milk()], offers_for_milk(), POLICY, 2)
    results = simulate(candidates, 500)
    assert all("reason" not in e for r in results for e in r.exposed)


def test_per_supplier_delay_only_moves_that_suppliers_lines():
    candidates, _ = build_candidates([milk()], offers_for_milk(), POLICY, 2)
    late_fast = simulate(candidates, 500, delays={"Fast": 3})
    fastest = next(r for r in late_fast if r.key == "all_fastest")
    cheapest = next(r for r in late_fast if r.key == "all_cheapest")
    assert fastest.bought[0].supplier == "Fast"
    assert fastest.bought[0].arrives_in_days == 4
    assert fastest.bought[0].stockout_days == 2
    assert cheapest.bought[0].supplier == "Slow"
    assert cheapest.bought[0].arrives_in_days == 2
    assert cheapest.bought[0].stockout_days == 0


def test_global_and_per_supplier_delays_add_up():
    candidates, _ = build_candidates([milk()], offers_for_milk(), POLICY, 2)
    fastest = next(r for r in simulate(candidates, 500, delay_days=1, delays={"Fast": 1}) if r.key == "all_fastest")
    assert fastest.bought[0].arrives_in_days == 3


def test_an_unfilled_item_counts_as_exposed_in_every_strategy():
    results = simulate([], 500, unfilled=[Unfilled("Milk", 2.0, "Slow", 3.0)])
    for r in results:
        assert r.exposed == [{"item": "Milk", "stockout_days": 1.0, "reason": "no_supplier"}]


def test_unfilled_exposure_has_no_duration_when_no_supplier_is_left():
    results = simulate([], 500, unfilled=[Unfilled("Milk", 2.0, None, None)])
    assert results[0].exposed == [{"item": "Milk", "stockout_days": None, "reason": "no_supplier"}]


def test_a_late_fastest_supplier_lengthens_the_unfilled_gap():
    results = simulate([], 500, delays={"Slow": 2}, unfilled=[Unfilled("Milk", 2.0, "Slow", 3.0)])
    assert results[0].exposed[0]["stockout_days"] == 3.0


# ---- API: the stress test on the demo data ----

def test_no_stress_leaves_the_demo_result_alone():
    result = lab()
    assert result["stress"]["active"] is False
    assert result["unfilled"] == []
    assert scenario(result, "critical_only")["spend"] == 259.8
    assert all(s["exposed"] == [] for s in result["scenarios"])


def test_switching_off_the_only_eligible_supplier_exposes_the_item():
    result = lab(unavailable_suppliers=["FreshMart"])
    assert result["stress"]["unavailable_suppliers"] == ["FreshMart"]
    assert result["unfilled"] == [
        {"item": "Butter", "days_left": 1.0, "fastest_supplier": "BakersChoice", "fastest_lead_days": 2.0}
    ]
    for s in result["scenarios"]:
        assert {"item": "Butter", "stockout_days": 1.0, "reason": "no_supplier"} in s["exposed"]
        assert all(l["supplier"] != "FreshMart" for l in s["bought"])


def test_critical_only_buys_nothing_when_the_only_critical_item_cannot_be_filled():
    critical = scenario(lab(unavailable_suppliers=["FreshMart"]), "critical_only")
    assert critical["bought"] == []
    assert critical["spend"] == 0


def test_a_late_supplier_exposes_only_what_it_was_going_to_deliver():
    result = lab(supplier_delays={"FreshMart": 2})
    cheapest = scenario(result, "all_cheapest")
    assert line(cheapest, "Butter")["arrives_in_days"] == 3.0
    assert line(cheapest, "Butter")["stockout_days"] == 2.0
    assert line(cheapest, "Flour")["supplier"] == "BakersChoice"
    assert line(cheapest, "Flour")["stockout_days"] == 0
    assert cheapest["exposed"] == [{"item": "Butter", "stockout_days": 2.0}]


def test_the_per_supplier_delay_stacks_with_the_all_suppliers_delay():
    cheapest = scenario(lab(supplier_delay_days=1, supplier_delays={"FreshMart": 1}), "all_cheapest")
    assert line(cheapest, "Butter")["arrives_in_days"] == 3.0
    assert line(cheapest, "Flour")["arrives_in_days"] == 3.0


def test_zero_delays_are_not_reported_as_stress():
    result = lab(supplier_delays={"FreshMart": 0})
    assert result["stress"]["supplier_delays"] == {}
    assert result["stress"]["active"] is False


def test_higher_demand_uses_stock_faster():
    result = lab(demand_change_pct=30)
    assert result["stress"]["demand_change_pct"] == 30
    assert result["unfilled"][0]["item"] == "Butter"
    assert result["unfilled"][0]["days_left"] == pytest.approx(0.769, abs=0.001)
    assert scenario(result, "fit_budget")["spend"] == 373.2


def test_lower_demand_stops_healthy_items_turning_into_purchases():
    """With demand halved, flour and boxes last longer than the fastest supplier needs. A slow
    supplier's large minimum order must not turn them back into 'buy' lines."""
    result = lab(demand_change_pct=-50)
    assert result["unfilled"] == []
    bought = {l["item"] for l in scenario(result, "all_cheapest")["bought"]}
    assert bought == {"Butter"}
    assert scenario(result, "all_cheapest")["spend"] == 96.6


def test_a_healthy_item_is_not_a_candidate_even_if_a_slow_supplier_would_plan_an_order():
    flour = Item("Flour", "Dry goods", "kg", stock=120, daily_usage=20, incoming=0, unit_cost=0.9, criticality=3)
    offers = {
        "Flour": [
            Supplier("Fast", 0.95, 1, min_order_qty=100, delivery_fee=15),
            Supplier("Slow", 0.70, 5, min_order_qty=500, delivery_fee=40),
        ]
    }
    candidates, unfillable = build_candidates([flour], offers, POLICY, 3)
    assert candidates == [] and unfillable == []


@pytest.mark.parametrize(
    "body",
    [
        {"supplier_delays": {"FreshMart": 15}},
        {"supplier_delays": {"FreshMart": -1}},
        {"demand_change_pct": 101},
        {"demand_change_pct": -51},
    ],
)
def test_out_of_range_stress_inputs_are_rejected(body):
    assert client.post("/lab/simulate", json=body).status_code == 422


def test_unknown_supplier_names_are_ignored_not_trusted():
    result = lab(unavailable_suppliers=["Nobody Ltd"], supplier_delays={"Nobody Ltd": 3})
    assert scenario(result, "critical_only")["spend"] == 259.8
    assert all(s["exposed"] == [] for s in result["scenarios"])


def test_the_stress_test_never_creates_orders_or_changes_stock():
    stock_before = client.get("/stock").json()
    lab(unavailable_suppliers=["FreshMart"], supplier_delays={"BakersChoice": 4}, demand_change_pct=50)
    assert client.get("/orders").json() == []
    assert client.get("/stock").json() == stock_before


# ---- API: turning a stressed plan into proposals ----

def test_proposals_from_a_stressed_plan_avoid_the_switched_off_supplier_and_say_so():
    body = client.post(
        "/lab/orders", json={"scenario": "fit_budget", "unavailable_suppliers": ["FreshMart"]}
    ).json()
    assert body["created"]
    for order in body["created"]:
        assert order["supplier_name"] != "FreshMart"
        assert order["decision"]["chosen"]["supplier"] == order["supplier_name"]
        assert any("switched off: FreshMart" in a for a in order["decision"]["assumptions"])
        assert order["status"] == "PENDING_APPROVAL"


def test_a_demand_stress_is_written_into_the_record_and_matches_the_order():
    body = client.post("/lab/orders", json={"scenario": "fit_budget", "demand_change_pct": 30}).json()
    flour = next(o for o in body["created"] if o["item"] == "Flour")
    assumptions = " ".join(flour["decision"]["assumptions"])
    assert "demand +30%" in assumptions
    assert "52 kg a day" in assumptions
    # The stressed figure must not be passed off as the recorded average.
    assert "52 kg a day, the average on record +30% for the stress test" in assumptions
    assert "the average on record." not in assumptions
    assert flour["decision"]["chosen"]["qty"] == flour["qty"]
    assert flour["decision"]["chosen"]["total"] == flour["total"]


def test_late_supplier_stress_is_recorded_too():
    body = client.post(
        "/lab/orders", json={"scenario": "fit_budget", "supplier_delays": {"FreshMart": 2}}
    ).json()
    butter = next(o for o in body["created"] if o["item"] == "Butter")
    assert any("FreshMart delivers 2 days late" in a for a in butter["decision"]["assumptions"])


def test_an_unstressed_proposal_has_no_stress_lines():
    body = client.post("/lab/orders", json={"scenario": "critical_only"}).json()
    assert not any("Stress test" in a for a in body["created"][0]["decision"]["assumptions"])


# ---- API: supplier rows for the grid ----

def test_supplier_rows_list_only_approved_suppliers_with_their_history():
    rows = {r["name"]: r for r in client.get("/lab/suppliers").json()["suppliers"]}
    assert set(rows) == {"BakersChoice", "Budget Bulk", "FreshMart", "QuickPack"}
    assert rows["FreshMart"]["reliability"] == 0.92
    assert rows["FreshMart"]["deliveries_on_record"] == 12
    assert rows["QuickPack"]["reliability"] is None
    assert rows["QuickPack"]["deliveries_on_record"] == 2


def test_supplier_rows_show_where_one_supplier_is_the_only_option():
    rows = {r["name"]: r for r in client.get("/lab/suppliers").json()["suppliers"]}
    assert rows["FreshMart"]["only_option_for"] == ["Butter"]
    assert rows["QuickPack"]["only_option_for"] == ["Paper bags"]
    assert rows["BakersChoice"]["only_option_for"] == []


def test_supplier_rows_report_their_fastest_lead_time_and_items():
    rows = {r["name"]: r for r in client.get("/lab/suppliers").json()["suppliers"]}
    assert rows["FreshMart"]["fastest_lead_days"] == 1
    assert rows["Budget Bulk"]["fastest_lead_days"] == 5
    assert "Butter" in rows["FreshMart"]["items"]
    assert "Butter" not in rows["QuickPack"]["items"]


# ---- API: the purchases ledger ----

def test_purchases_ledger_lists_demo_history_with_its_source():
    body = client.get("/purchases").json()
    assert body["demo_data"] is True
    assert len(body["purchases"]) == 72
    assert all(p["is_demo"] for p in body["purchases"])
    assert {"item", "category", "supplier", "qty", "total", "purchased_on", "is_demo"} <= set(body["purchases"][0])


def test_a_real_purchase_appears_in_the_ledger_marked_as_real():
    with db.connect() as conn:
        db.record_purchase(conn, "Flour", "BakersChoice", 100, 108.0)
    rows = client.get("/purchases").json()["purchases"]
    real = [p for p in rows if not p["is_demo"]]
    assert len(real) == 1
    assert real[0]["item"] == "Flour" and real[0]["total"] == 108.0 and real[0]["category"] == "Dry goods"
