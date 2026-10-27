from app.policy import Policy, check_order
from app.suppliers import Supplier

POLICY = Policy(max_auto_spend=500, budget=2000)


def test_small_order_is_allowed_without_approval():
    s = Supplier("Acme", unit_price=2, lead_time_days=2)
    result = check_order(s, qty=100, policy=POLICY)  # $200
    assert result.allowed is True
    assert result.needs_approval is False


def test_order_at_the_limit_needs_no_approval():
    s = Supplier("Acme", unit_price=2, lead_time_days=2)
    result = check_order(s, qty=250, policy=POLICY)  # exactly $500
    assert result.needs_approval is False


def test_order_over_auto_limit_needs_approval():
    s = Supplier("Acme", unit_price=2, lead_time_days=2)
    result = check_order(s, qty=300, policy=POLICY)  # $600
    assert result.allowed is True
    assert result.needs_approval is True
    assert len(result.reasons) == 1


def test_order_over_budget_is_blocked():
    s = Supplier("Acme", unit_price=2, lead_time_days=2)
    result = check_order(s, qty=1500, policy=POLICY)  # $3000
    assert result.allowed is False


def test_unapproved_supplier_is_blocked():
    s = Supplier("Shady", unit_price=1, lead_time_days=1, approved=False)
    result = check_order(s, qty=10, policy=POLICY)
    assert result.allowed is False
    assert "approved list" in result.reasons[0]