from datetime import date

from app.analytics import (
    budget_status,
    excess_stock,
    last_months,
    monthly_spend,
    spend_by_category,
    spent_in_month,
)

PURCHASES = [
    {"category": "Dairy", "total": 100.0, "purchased_on": "2026-09-10", "is_demo": True},
    {"category": "Dairy", "total": 50.0, "purchased_on": "2026-10-02", "is_demo": True},
    {"category": "Packaging", "total": 80.0, "purchased_on": "2026-10-20", "is_demo": True},
    {"category": "Packaging", "total": 40.0, "purchased_on": "2026-10-28", "is_demo": False},
    {"category": "Dairy", "total": 999.0, "purchased_on": "2026-01-05", "is_demo": True},
]


def test_last_months_ends_with_the_current_month():
    assert last_months(date(2026, 11, 5), 3) == ["2026-09", "2026-10", "2026-11"]


def test_last_months_crosses_a_year_boundary():
    assert last_months(date(2026, 2, 14), 4) == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_monthly_spend_separates_real_orders_from_demo_history():
    rows = monthly_spend(PURCHASES, ["2026-09", "2026-10", "2026-11"])
    assert rows == [
        {"month": "2026-09", "total": 100.0, "real_total": 0.0},
        {"month": "2026-10", "total": 170.0, "real_total": 40.0},
        {"month": "2026-11", "total": 0.0, "real_total": 0.0},
    ]


def test_purchases_outside_the_window_are_ignored():
    rows = monthly_spend(PURCHASES, ["2026-09", "2026-10"])
    assert sum(r["total"] for r in rows) == 270.0   # the January purchase is not counted


def test_spend_by_category_is_sorted_and_windowed():
    rows = spend_by_category(PURCHASES, ["2026-09", "2026-10"])
    assert rows == [
        {"category": "Dairy", "total": 150.0},
        {"category": "Packaging", "total": 120.0},
    ]


def test_spent_in_month():
    assert spent_in_month(PURCHASES, "2026-10") == 170.0
    assert spent_in_month(PURCHASES, "2026-12") == 0


def test_budget_status_within_budget():
    b = budget_status(1000, 250, "2026-10")
    assert b["remaining"] == 750
    assert b["used_pct"] == 25
    assert b["over_budget"] is False


def test_budget_status_over_budget_has_negative_remaining():
    b = budget_status(1000, 1200, "2026-10")
    assert b["remaining"] == -200
    assert b["over_budget"] is True


def test_budget_status_with_no_budget_does_not_divide_by_zero():
    assert budget_status(0, 50, "2026-10")["used_pct"] == 0


def view(name, stock, usage, cost, days):
    return {"item": name, "unit": "kg", "stock": stock, "daily_usage": usage, "unit_cost": cost, "days_left": days}


def test_excess_is_stock_beyond_thirty_days_of_use():
    result = excess_stock([view("Cocoa", 120, 2, 7.5, 60), view("Flour", 120, 40, 1, 3)])
    assert [i["item"] for i in result["items"]] == ["Cocoa"]
    assert result["items"][0]["excess_qty"] == 60
    assert result["items"][0]["excess_value"] == 450
    assert result["value"] == 450


def test_exactly_thirty_days_is_not_excess():
    assert excess_stock([view("X", 300, 10, 1, 30)])["items"] == []


def test_items_with_no_usage_are_not_called_excess():
    assert excess_stock([view("X", 500, 0, 1, None)])["items"] == []


def test_biggest_excess_comes_first():
    result = excess_stock([view("Small", 100, 1, 1, 100), view("Big", 1000, 1, 5, 1000)])
    assert [i["item"] for i in result["items"]] == ["Big", "Small"]
