from app.suppliers import Supplier, arrives_in_time, best_supplier, eligible_suppliers


def test_arrives_before_runout():
    s = Supplier("Acme", unit_price=2, lead_time_days=2)
    assert arrives_in_time(s, days_of_stock_left=3) is True


def test_arrives_too_late():
    s = Supplier("Slowco", unit_price=1, lead_time_days=5)
    assert arrives_in_time(s, days_of_stock_left=3) is False


def test_no_usage_always_in_time():
    s = Supplier("Acme", unit_price=2, lead_time_days=10)
    assert arrives_in_time(s, days_of_stock_left=None) is True


def test_unapproved_supplier_is_excluded():
    suppliers = [
        Supplier("Cheap but unapproved", unit_price=1, lead_time_days=1, approved=False),
        Supplier("Acme", unit_price=2, lead_time_days=2),
    ]
    result = eligible_suppliers(suppliers, days_of_stock_left=3)
    assert [s.name for s in result] == ["Acme"]


def test_late_supplier_is_excluded():
    suppliers = [
        Supplier("Slowco", unit_price=1, lead_time_days=5),
        Supplier("Acme", unit_price=2, lead_time_days=2),
    ]
    result = eligible_suppliers(suppliers, days_of_stock_left=3)
    assert [s.name for s in result] == ["Acme"]


def test_best_supplier_is_cheapest_eligible():
    suppliers = [
        Supplier("Pricey", unit_price=3, lead_time_days=1),
        Supplier("Acme", unit_price=2, lead_time_days=2),
        Supplier("Slowco", unit_price=1, lead_time_days=5),
    ]
    assert best_supplier(suppliers, days_of_stock_left=3).name == "Acme"


def test_tie_goes_to_faster_delivery():
    suppliers = [
        Supplier("Slower", unit_price=2, lead_time_days=3),
        Supplier("Faster", unit_price=2, lead_time_days=1),
    ]
    assert best_supplier(suppliers, days_of_stock_left=5).name == "Faster"


def test_no_eligible_supplier_returns_none():
    suppliers = [Supplier("Slowco", unit_price=1, lead_time_days=5)]
    assert best_supplier(suppliers, days_of_stock_left=3) is None
