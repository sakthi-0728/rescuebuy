from app.forecast import days_left, reorder_qty, risk_level

def test_bakery_example_three_days_left():
    assert days_left(stock=120, incoming=0, daily_usage=40) == 3


def test_incoming_stock_extends_runway():
    assert days_left(stock=120, incoming=80, daily_usage=40) == 5


def test_zero_usage_never_runs_out():
    assert days_left(stock=100, incoming=0, daily_usage=0) is None


def test_critical_when_runs_out_before_delivery():
    assert risk_level(3, lead_time_days=3) == "critical"


def test_warning_when_close_to_lead_time():
    assert risk_level(4, lead_time_days=3, buffer_days=2) == "warning"


def test_ok_when_plenty_of_stock():
    assert risk_level(10, lead_time_days=3) == "ok"


def test_no_usage_is_ok():
    assert risk_level(None, lead_time_days=3) == "ok"

def test_reorder_qty_basic():
    assert reorder_qty(120, 0, 40, lead_time_days=2, buffer_days=3) == 80


def test_reorder_accounts_for_incoming():
    assert reorder_qty(120, 50, 40, lead_time_days=2, buffer_days=3) == 30


def test_no_reorder_when_well_stocked():
    assert reorder_qty(500, 0, 40, lead_time_days=2, buffer_days=3) == 0


def test_budget_caps_quantity():
    # wants 80 units, but $100 at $2 each only buys 50
    assert reorder_qty(120, 0, 40, 2, 3, unit_price=2, budget=100) == 50