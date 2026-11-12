"""API behaviour added for explainability: decision records, verified PayPal events on orders,
the briefing's top action and the analytics fields behind the insight tiles."""
import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

client = TestClient(app)

BOXES = "Bakery boxes"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RESCUEBUY_DB", str(tmp_path / "test.db"))
    db.init_db(force=True)


@pytest.fixture(autouse=True)
def no_real_ai(monkeypatch):
    def broken_client(api_key=None):
        raise RuntimeError("AI disabled in tests")

    monkeypatch.setattr("app.ai.genai.Client", broken_client)
    monkeypatch.setattr(
        "app.compare.choose_supplier",
        lambda opts: {"name": opts[0]["name"], "reason": "Test choice."},
    )


@pytest.fixture(autouse=True)
def allow_webhook_signatures(monkeypatch):
    monkeypatch.setattr("app.main.verify_webhook_signature", lambda headers, event: True)


def fake_paypal_order(amount, description):
    return {"id": "PPORDER1", "links": [{"rel": "payer-action", "href": "https://example.com/approve"}]}


def fake_authorize(paypal_order_id):
    return {"purchase_units": [{"payments": {"authorizations": [{"id": "AUTH1"}]}}]}


def fake_capture(authorization_id):
    return {"id": "CAP1", "status": "COMPLETED"}


def event(event_id, event_type, resource_id, summary="PayPal event"):
    return {"id": event_id, "event_type": event_type, "summary": summary, "resource": {"id": resource_id}}


def authorize_order_one(monkeypatch, item=BOXES, supplier="BakersChoice"):
    monkeypatch.setattr("app.main.create_paypal_order", fake_paypal_order)
    monkeypatch.setattr("app.main.authorize_paypal_order", fake_authorize)
    client.post("/orders", json={"item": item, "supplier": supplier})
    client.post("/orders/1/approve")
    client.post("/orders/1/pay")
    client.get("/paypal/return", params={"token": "PPORDER1"}, follow_redirects=False)


# ---- Decision records ----

def test_new_order_carries_a_decision_record():
    order = client.post("/orders", json={"item": BOXES, "supplier": "BakersChoice"}).json()
    decision = order["decision"]
    assert decision["chosen"]["supplier"] == "BakersChoice"
    assert decision["chosen"]["total"] == order["total"]
    assert decision["chosen_by"] == "owner"
    assert decision["budget_remaining_before"] == 422.1


def test_record_lists_rejected_suppliers_with_reasons():
    decision = client.post("/orders", json={"item": BOXES, "supplier": "BakersChoice"}).json()["decision"]
    rejected = {r["name"]: r["reasons"] for r in decision["rejected"]}
    assert "Not on the approved supplier list" in rejected["Shady Traders"]


def test_record_is_not_duplicated_inside_the_timeline():
    order = client.post("/orders", json={"item": BOXES, "supplier": "BakersChoice"}).json()
    assert all("record" not in e for e in order["timeline"])
    assert order["timeline"][0]["type"] == "ORDER_CREATED"


def test_record_survives_every_later_step_and_is_listed_with_the_order(monkeypatch):
    authorize_order_one(monkeypatch)
    listed = client.get("/orders").json()[0]
    assert listed["status"] == "AUTHORIZED"
    assert listed["decision"]["chosen"]["supplier"] == "BakersChoice"
    assert client.get("/orders/1").json()["decision"] == listed["decision"]


def test_without_a_named_supplier_the_record_says_who_chose():
    order = client.post("/orders", json={"item": BOXES}).json()
    assert order["decision"]["chosen_by"] in ("gemini", "fallback", "rules")
    assert order["decision"]["reason"]


def test_decision_lab_orders_carry_a_record_naming_the_strategy():
    body = client.post("/lab/orders", json={"scenario": "fit_budget"}).json()
    assert body["created"]
    for order in body["created"]:
        assert order["decision"]["chosen_by"] == "decision_lab"
        assert "Fit the budget by urgency" in order["decision"]["reason"]
        assert order["decision"]["chosen"]["supplier"] == order["supplier_name"]


def test_record_is_stored_in_the_database_not_rebuilt():
    client.post("/orders", json={"item": BOXES, "supplier": "BakersChoice"})
    with db.connect() as conn:
        order = db.get_order(conn, 1)
    assert order.timeline[0]["record"]["chosen"]["supplier"] == "BakersChoice"


# ---- Verified PayPal events on an order ----

def test_webhook_stores_the_resource_id():
    client.post("/webhooks/paypal", json=event("WH-1", "PAYMENT.AUTHORIZATION.CREATED", "AUTH1"))
    with db.connect() as conn:
        assert [e["resource_id"] for e in db.events_for_resources(conn, ["AUTH1"])] == ["AUTH1"]


def test_order_shows_only_events_for_its_own_paypal_ids(monkeypatch):
    authorize_order_one(monkeypatch)
    client.post("/webhooks/paypal", json=event("WH-1", "CHECKOUT.ORDER.APPROVED", "PPORDER1"))
    client.post("/webhooks/paypal", json=event("WH-2", "PAYMENT.AUTHORIZATION.CREATED", "AUTH1"))
    client.post("/webhooks/paypal", json=event("WH-3", "PAYMENT.CAPTURE.COMPLETED", "SOMEONE-ELSES"))
    events = client.get("/orders/1").json()["paypal_events"]
    assert [e["type"] for e in events] == ["CHECKOUT.ORDER.APPROVED", "PAYMENT.AUTHORIZATION.CREATED"]


def test_order_without_payment_has_no_paypal_events():
    client.post("/orders", json={"item": BOXES, "supplier": "BakersChoice"})
    client.post("/webhooks/paypal", json=event("WH-1", "PAYMENT.CAPTURE.COMPLETED", "CAP1"))
    assert client.get("/orders/1").json()["paypal_events"] == []


def test_duplicate_delivery_shows_once(monkeypatch):
    authorize_order_one(monkeypatch)
    client.post("/webhooks/paypal", json=event("WH-1", "PAYMENT.AUTHORIZATION.CREATED", "AUTH1"))
    client.post("/webhooks/paypal", json=event("WH-1", "PAYMENT.AUTHORIZATION.CREATED", "AUTH1"))
    assert len(client.get("/orders/1").json()["paypal_events"]) == 1


def test_unverified_events_never_appear(monkeypatch):
    authorize_order_one(monkeypatch)
    monkeypatch.setattr("app.main.verify_webhook_signature", lambda headers, event: False)
    response = client.post("/webhooks/paypal", json=event("WH-9", "PAYMENT.AUTHORIZATION.CREATED", "AUTH1"))
    assert response.status_code == 401
    assert client.get("/orders/1").json()["paypal_events"] == []


def test_capture_event_that_arrives_before_the_capture_is_stored_is_found_later(monkeypatch):
    authorize_order_one(monkeypatch)
    client.post("/webhooks/paypal", json=event("WH-5", "PAYMENT.CAPTURE.COMPLETED", "CAP1"))
    assert client.get("/orders/1").json()["paypal_events"] == []
    monkeypatch.setattr("app.main.capture_authorization", fake_capture)
    client.post("/orders/1/confirm-delivery")
    events = client.get("/orders/1").json()["paypal_events"]
    assert [e["type"] for e in events] == ["PAYMENT.CAPTURE.COMPLETED"]


def test_an_event_alone_never_moves_the_order_or_stock(monkeypatch):
    authorize_order_one(monkeypatch)
    client.post("/webhooks/paypal", json=event("WH-5", "PAYMENT.CAPTURE.COMPLETED", "CAP1"))
    order = client.get("/orders/1").json()
    assert order["status"] == "AUTHORIZED"
    assert client.get("/stock").json()[BOXES] == 600


def test_event_without_a_resource_is_still_recorded_but_matches_no_order():
    response = client.post("/webhooks/paypal", json={"id": "WH-7", "event_type": "X", "summary": "s"})
    assert response.json() == {"status": "received"}
    assert len(client.get("/events").json()) == 1


# ---- Briefing top action ----

def test_dashboard_top_action_is_the_most_urgent_item_with_a_supplier_that_arrives_in_time():
    action = client.get("/dashboard").json()["top_action"]
    assert action["item"] == "Butter"
    assert action["supplier"] == "FreshMart"
    assert action["lead_time_days"] == 1
    assert action["total"] == 259.8
    assert action["qty"] == 36
    assert action["fits_budget"] is True
    assert action["budget_remaining"] == 422.1


def test_top_action_skips_an_item_that_already_has_an_order():
    client.post("/orders", json={"item": "Butter", "supplier": "FreshMart"})
    action = client.get("/dashboard").json()["top_action"]
    assert action["item"] == "Flour"


def test_top_action_is_none_when_nothing_needs_reordering():
    with db.connect() as conn:
        conn.execute("UPDATE items SET stock = daily_usage * 60")
    body = client.get("/dashboard").json()
    assert body["top_action"] is None


# ---- Analytics fields behind the insight tiles ----

def test_analytics_names_the_items_at_risk():
    risk = client.get("/analytics").json()["stock_risk"]
    assert risk["critical"] == ["Butter"]
    assert set(risk["low"]) == {"Flour", BOXES, "Yeast", "Paper bags"}


def test_excess_rows_include_the_stock_so_the_excess_can_be_shown_as_part_of_the_whole():
    rows = {r["item"]: r for r in client.get("/analytics").json()["excess"]["items"]}
    cocoa = rows["Cocoa powder"]
    assert cocoa["stock"] == 120
    assert cocoa["excess_qty"] == 60
    assert cocoa["excess_value"] == 450.0
    assert cocoa["unit_cost"] == 7.5
    assert cocoa["excess_qty"] * cocoa["unit_cost"] == cocoa["excess_value"]
