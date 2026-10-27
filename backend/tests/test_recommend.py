from app.policy import Policy
from app.recommend import recommend
from app.suppliers import Supplier

POLICY = Policy(max_auto_spend=500, budget=2000)

SUPPLIERS = [
    Supplier("Pricey", unit_price=3, lead_time_days=1),
    Supplier("Acme", unit_price=2, lead_time_days=2),
    Supplier("Slowco", unit_price=1, lead_time_days=5),
]


def test_bakery_example_recommends_acme():
    # 120 boxes, 40/day -> 3 days left. Slowco is too late, Acme is cheapest in time.
    r = recommend(120, 0, 40, SUPPLIERS, POLICY, buffer_days=3)
    assert r.days_left == 3
    assert r.supplier.name == "Acme"
    assert r.qty == 80          # 40 * (2 + 3) - 120
    assert r.total == 160
    assert r.policy.allowed is True
    assert r.policy.needs_approval is False


def test_zero_stock_has_no_eligible_supplier():
    r = recommend(0, 0, 200, SUPPLIERS, POLICY, buffer_days=3)
    assert r.supplier is None  # 0 days left, nobody arrives in time


def test_well_stocked_needs_no_order():
    r = recommend(1000, 0, 40, SUPPLIERS, POLICY, buffer_days=3)
    assert r.qty == 0
    assert r.message == "Stock is sufficient. No order needed."


def test_no_eligible_supplier_escalates():
    only_slow = [Supplier("Slowco", unit_price=1, lead_time_days=5)]
    r = recommend(120, 0, 40, only_slow, POLICY)
    assert r.supplier is None
    assert r.message == "No eligible supplier. Escalate to the owner."

def test_big_order_needs_approval():
    # 600 boxes, 200/day -> 3 days left. Acme (2 days) is in time.
    # qty = 200 * (2 + 3) - 600 = 400, total = $800, above the $500 limit.
    r = recommend(600, 0, 200, SUPPLIERS, POLICY, buffer_days=3)
    assert r.supplier.name == "Acme"
    assert r.qty == 400
    assert r.total == 800
    assert r.policy.allowed is True
    assert r.policy.needs_approval is True