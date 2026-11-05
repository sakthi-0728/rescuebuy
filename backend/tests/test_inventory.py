from datetime import date

from app.inventory import (
    Item,
    build_alerts,
    days_until,
    expiring_unused,
    item_view,
    summarize,
)

TODAY = date(2026, 11, 1)


def make_item(**overrides):
    base = dict(
        name="Flour", category="Dry goods", unit="kg", stock=120, daily_usage=40,
        incoming=0, unit_cost=0.9, criticality=3,
    )
    base.update(overrides)
    return Item(**base)


def view(item, lead=1, buffer_days=3):
    return item_view(item, lead, buffer_days, TODAY)


def test_view_computes_days_left_and_value():
    v = view(make_item())
    assert v["days_left"] == 3
    assert v["inventory_value"] == 108.0
    assert v["risk"] == "warning"


def test_critical_when_runout_is_before_the_fastest_delivery():
    assert view(make_item(stock=12, daily_usage=12), lead=2)["risk"] == "critical"


def test_item_without_suppliers_is_still_assessed():
    v = view(make_item(stock=500), lead=None)
    assert v["risk"] == "ok"
    assert v["fastest_lead_time_days"] is None


def test_days_until_needs_real_expiry_data():
    assert days_until(None, TODAY) is None
    assert days_until("2026-11-04", TODAY) == 3
    assert days_until("2026-10-30", TODAY) == -2


def test_expiring_unused_quantity():
    assert expiring_unused(120, 10, 6) == 60   # uses 60, 60 left at expiry
    assert expiring_unused(30, 10, 6) == 0     # used up in time
    assert expiring_unused(30, 10, None) == 0  # no expiry data, no claim
    assert expiring_unused(30, 10, -1) == 30   # already expired


def test_stockout_alert_has_reason_and_action():
    alerts = build_alerts([view(make_item())])
    assert len(alerts) == 1
    a = alerts[0]
    assert a["kind"] == "stockout"
    assert a["severity"] == "warning"
    assert a["action"] == "review_reorder"
    assert "About 3 days of stock left" in a["reason"]
    assert "needs 1 day" in a["reason"]


def test_healthy_item_has_no_alert():
    assert build_alerts([view(make_item(stock=1000))]) == []


def test_no_expiry_data_means_no_expiry_alert():
    alerts = build_alerts([view(make_item(stock=1000, expiry_date=None))])
    assert alerts == []


def test_expiry_alert_says_how_much_may_go_unused():
    item = make_item(name="Eggs", unit="trays", stock=120, daily_usage=10, expiry_date="2026-11-07")
    alerts = build_alerts([view(item, lead=1)])
    assert len(alerts) == 1
    assert alerts[0]["kind"] == "expiry"
    assert alerts[0]["severity"] == "warning"
    assert "60 trays may go unused" in alerts[0]["reason"]
    assert alerts[0]["action"] is None


def test_expiry_alert_when_stock_will_be_used_in_time():
    item = make_item(stock=20, daily_usage=10, expiry_date="2026-11-03")
    alerts = [a for a in build_alerts([view(item, lead=1)]) if a["kind"] == "expiry"]
    assert len(alerts) == 1
    assert "used in time" in alerts[0]["reason"]


def test_no_expiry_alert_when_far_away_and_nothing_wasted():
    item = make_item(stock=100, daily_usage=40, expiry_date="2026-11-07")
    assert [a for a in build_alerts([view(item, lead=1)]) if a["kind"] == "expiry"] == []


def test_expired_stock_is_critical():
    item = make_item(stock=1000, expiry_date="2026-10-30")
    a = build_alerts([view(item)])[0]
    assert a["severity"] == "critical"
    assert "Expired 2 days ago" in a["reason"]


def test_critical_alerts_come_first_then_stockouts_then_criticality():
    flour = make_item(name="Flour", stock=120, daily_usage=40, criticality=3)       # warning
    butter = make_item(name="Butter", stock=12, daily_usage=12, criticality=3)      # critical
    boxes = make_item(name="Boxes", stock=600, daily_usage=200, criticality=2)      # warning
    eggs = make_item(name="Eggs", stock=120, daily_usage=10, criticality=3,
                     expiry_date="2026-11-07")                                      # expiry warning
    views = [view(x) for x in (eggs, boxes, flour, butter)]
    order = [(a["item"], a["kind"]) for a in build_alerts(views)]
    assert order == [
        ("Butter", "stockout"),
        ("Flour", "stockout"),
        ("Boxes", "stockout"),
        ("Eggs", "expiry"),
    ]


def test_summary_counts():
    views = [
        view(make_item(name="A", stock=12, daily_usage=12)),   # critical
        view(make_item(name="B")),                             # warning
        view(make_item(name="C", stock=1000)),                 # ok
    ]
    alerts = build_alerts(views)
    s = summarize(views, alerts, open_orders=2)
    assert s["item_count"] == 3
    assert s["critical_count"] == 1
    assert s["low_count"] == 1
    assert s["open_orders"] == 2
    assert s["inventory_value"] == round(12 * 0.9 + 108 + 900, 2)


def test_alert_wording_handles_one_day_and_fractions():
    one = build_alerts([view(make_item(stock=12, daily_usage=12), lead=2)])[0]
    assert "About 1 day of stock left" in one["reason"]
    part = build_alerts([view(make_item(stock=10, daily_usage=12), lead=2)])[0]
    assert "About 0.8 days of stock left" in part["reason"]


def test_alert_carries_the_open_order_from_the_view():
    v = view(make_item())
    v["open_order"] = {"id": 7, "status": "APPROVED"}
    assert build_alerts([v])[0]["open_order"] == {"id": 7, "status": "APPROVED"}
