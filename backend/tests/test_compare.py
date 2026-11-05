from app.compare import (
    build_options,
    cheapest_option,
    evaluate_suppliers,
    pick_option,
    plan_order,
)
from app.policy import Policy
from app.suppliers import Supplier

POLICY = Policy(max_auto_spend=500, budget=2000)

SUPPLIERS = [
    Supplier("Pricey", unit_price=3, lead_time_days=1),
    Supplier("Acme", unit_price=2, lead_time_days=2),
    Supplier("Slowco", unit_price=1, lead_time_days=5),
]


def names(options):
    return [o.supplier.name for o in options]


def test_options_for_bakery_example():
    options = build_options(120, 0, 40, SUPPLIERS, POLICY, buffer_days=3)
    assert names(options) == ["Pricey", "Acme"]
    assert [o.qty for o in options] == [40, 80]
    assert [o.total for o in options] == [120, 160]


def test_late_supplier_is_not_an_option():
    options = build_options(120, 0, 40, SUPPLIERS, POLICY, buffer_days=3)
    assert "Slowco" not in names(options)


def test_unapproved_supplier_is_not_an_option():
    suppliers = SUPPLIERS + [Supplier("Shady", 0.5, 1, approved=False)]
    options = build_options(120, 0, 40, suppliers, POLICY, buffer_days=3)
    assert "Shady" not in names(options)


def test_supplier_without_enough_stock_is_dropped():
    suppliers = [
        Supplier("Acme", unit_price=2, lead_time_days=2, stock_available=50),
        Supplier("Pricey", unit_price=3, lead_time_days=1),
    ]
    options = build_options(120, 0, 40, suppliers, POLICY, buffer_days=3)
    assert names(options) == ["Pricey"]  # Acme needs 80 but has 50


def test_well_stocked_means_no_options():
    assert build_options(1000, 0, 40, SUPPLIERS, POLICY, buffer_days=3) == []


def test_options_over_approval_limit_are_kept_and_flagged():
    options = build_options(600, 0, 200, SUPPLIERS, POLICY, buffer_days=3)
    assert names(options) == ["Pricey", "Acme"]
    assert all(o.policy.needs_approval for o in options)


def test_new_supplier_fields_have_defaults():
    s = Supplier("Acme", 2, 2)
    assert s.stock_available is None
    assert s.reliability is None  # unknown until there is delivery history
    assert s.min_order_qty == 1
    assert s.delivery_fee == 0


def bakery_options():
    return build_options(120, 0, 40, SUPPLIERS, POLICY, buffer_days=3)


def test_cheapest_option_uses_total_not_unit_price():
    assert cheapest_option(bakery_options()).supplier.name == "Pricey"


def test_pick_uses_ai_choice(monkeypatch):
    monkeypatch.setattr(
        "app.compare.choose_supplier",
        lambda opts: {"name": "Acme", "reason": "More reliable."},
    )
    choice = pick_option(bakery_options())
    assert choice.option.supplier.name == "Acme"
    assert choice.reason == "More reliable."
    assert choice.source == "gemini"


def test_pick_falls_back_when_ai_unavailable(monkeypatch):
    monkeypatch.setattr("app.compare.choose_supplier", lambda opts: None)
    choice = pick_option(bakery_options())
    assert choice.option.supplier.name == "Pricey"
    assert choice.source == "fallback"


def test_pick_rejects_ai_choice_not_on_the_list(monkeypatch):
    monkeypatch.setattr(
        "app.compare.choose_supplier",
        lambda opts: {"name": "Slowco", "reason": "Cheapest."},
    )
    choice = pick_option(bakery_options())
    assert choice.option.supplier.name == "Pricey"
    assert choice.source == "fallback"


def test_single_option_skips_ai(monkeypatch):
    def must_not_be_called(opts):
        raise AssertionError("AI should not be called")

    monkeypatch.setattr("app.compare.choose_supplier", must_not_be_called)
    options = build_options(
        120, 0, 40, [Supplier("Acme", unit_price=2, lead_time_days=2)],
        POLICY, buffer_days=3,
    )
    choice = pick_option(options)
    assert choice.option.supplier.name == "Acme"
    assert choice.source == "rules"


def test_no_options_means_no_choice():
    assert pick_option([]) is None


def test_ai_receives_totals_and_unknown_reliability(monkeypatch):
    seen = []

    def fake_choose(opts):
        seen.extend(opts)
        return None

    monkeypatch.setattr("app.compare.choose_supplier", fake_choose)
    pick_option(bakery_options())
    assert [o["name"] for o in seen] == ["Pricey", "Acme"]
    assert [o["total"] for o in seen] == [120, 160]
    assert seen[0]["reliability"] is None  # no history, so unknown, not invented


def test_plan_uses_ai_choice(monkeypatch):
    monkeypatch.setattr(
        "app.compare.choose_supplier",
        lambda opts: {"name": "Acme", "reason": "More reliable."},
    )
    plan = plan_order(120, 0, 40, SUPPLIERS, POLICY, buffer_days=3)
    assert plan.days_left == 3
    assert plan.choice.option.supplier.name == "Acme"
    assert plan.message == "Order recommended."


def test_plan_falls_back_when_ai_is_down(monkeypatch):
    monkeypatch.setattr("app.compare.choose_supplier", lambda opts: None)
    plan = plan_order(120, 0, 40, SUPPLIERS, POLICY, buffer_days=3)
    assert plan.choice.option.supplier.name == "Pricey"
    assert plan.choice.source == "fallback"


def test_plan_with_no_eligible_supplier():
    plan = plan_order(0, 0, 200, SUPPLIERS, POLICY)
    assert plan.options == []
    assert plan.choice is None
    assert plan.message == "No eligible supplier. Escalate to the owner."


def test_plan_when_well_stocked():
    plan = plan_order(1000, 0, 40, SUPPLIERS, POLICY, buffer_days=3)
    assert plan.choice is None
    assert plan.rejected == []
    assert plan.message == "Stock is sufficient. No order needed."


def test_plan_when_no_supplier_can_fill_the_order():
    suppliers = [Supplier("Acme", unit_price=2, lead_time_days=2, stock_available=10)]
    plan = plan_order(120, 0, 40, suppliers, POLICY, buffer_days=3)
    assert plan.options == []
    assert plan.choice is None
    assert plan.message == "No supplier can fill this order within the rules. Escalate to the owner."


# ---- Hard checks, rejection reasons, minimum order, delivery fee ----

def rejected_reasons(rejected):
    return {r.name: r.reasons for r in rejected}


def test_every_supplier_is_an_option_or_a_rejection():
    suppliers = SUPPLIERS + [Supplier("Shady", 0.5, 1, approved=False)]
    options, rejected = evaluate_suppliers(120, 0, 40, suppliers, POLICY, buffer_days=3)
    assert names(options) == ["Pricey", "Acme"]
    assert [r.name for r in rejected] == ["Slowco", "Shady"]


def test_rejection_reasons_are_specific():
    suppliers = SUPPLIERS + [Supplier("Shady", 0.5, 1, approved=False)]
    _, rejected = evaluate_suppliers(120, 0, 40, suppliers, POLICY, buffer_days=3)
    reasons = rejected_reasons(rejected)
    assert reasons["Shady"] == ["Not on the approved supplier list"]
    assert "Delivers in 5 days" in reasons["Slowco"][0]
    assert "3.0 days" in reasons["Slowco"][0]


def test_minimum_order_rounds_the_quantity_up():
    suppliers = [Supplier("Acme", unit_price=2, lead_time_days=2, min_order_qty=100)]
    options, _ = evaluate_suppliers(120, 0, 40, suppliers, POLICY, buffer_days=3)
    assert options[0].qty == 100  # needed 80
    assert options[0].total == 200
    assert "minimum order of 100" in options[0].note


def test_minimum_order_can_make_a_supplier_unaffordable():
    suppliers = [Supplier("Acme", unit_price=2, lead_time_days=2, min_order_qty=2000)]
    options, rejected = evaluate_suppliers(120, 0, 40, suppliers, POLICY, buffer_days=3)
    assert options == []
    assert "exceeds budget" in rejected[0].reasons[0]


def test_delivery_fee_is_part_of_the_total():
    suppliers = [Supplier("Acme", unit_price=2, lead_time_days=2, delivery_fee=25)]
    options, _ = evaluate_suppliers(120, 0, 40, suppliers, POLICY, buffer_days=3)
    assert options[0].total == 185  # 80 x $2 + $25


def test_delivery_fee_can_change_which_supplier_is_cheapest():
    suppliers = [
        Supplier("LowPriceHighFee", unit_price=1.5, lead_time_days=2, delivery_fee=100),
        Supplier("HigherPriceFree", unit_price=2, lead_time_days=2),
    ]
    options, _ = evaluate_suppliers(120, 0, 40, suppliers, POLICY, buffer_days=3)
    assert cheapest_option(options).supplier.name == "HigherPriceFree"


def test_insufficient_supplier_stock_is_explained():
    suppliers = [Supplier("Acme", unit_price=2, lead_time_days=2, stock_available=10)]
    _, rejected = evaluate_suppliers(120, 0, 40, suppliers, POLICY, buffer_days=3)
    assert rejected[0].reasons == ["Only 10 available, 80 needed"]


def test_margin_days_shows_time_between_delivery_and_stockout():
    options, _ = evaluate_suppliers(120, 0, 40, SUPPLIERS, POLICY, buffer_days=3)
    by_name = {o.supplier.name: o for o in options}
    assert by_name["Pricey"].margin_days == 2.0  # runs out in 3 days, arrives in 1
    assert by_name["Acme"].margin_days == 1.0
