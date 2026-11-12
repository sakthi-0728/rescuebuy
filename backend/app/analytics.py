"""Purchasing analytics. Plain functions over plain data, so they are easy to test."""
from datetime import date

EXCESS_DAYS = 30  # stock beyond this many days of cover counts as excess


def last_months(today: date, n: int) -> list[str]:
    """The last n months as 'YYYY-MM', oldest first, ending with this month."""
    year, month = today.year, today.month
    months = []
    for _ in range(n):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(months))


def monthly_spend(purchases: list[dict], months: list[str]) -> list[dict]:
    """Spend per month. real_total is the part that came from real orders, not demo history."""
    totals = {m: {"total": 0.0, "real_total": 0.0} for m in months}
    for p in purchases:
        bucket = totals.get(p["purchased_on"][:7])
        if bucket is None:
            continue
        bucket["total"] += p["total"]
        if not p["is_demo"]:
            bucket["real_total"] += p["total"]
    return [
        {"month": m, "total": round(v["total"], 2), "real_total": round(v["real_total"], 2)}
        for m, v in totals.items()
    ]


def spend_by_category(purchases: list[dict], months: list[str]) -> list[dict]:
    wanted = set(months)
    totals: dict[str, float] = {}
    for p in purchases:
        if p["purchased_on"][:7] in wanted:
            totals[p["category"]] = totals.get(p["category"], 0.0) + p["total"]
    rows = [{"category": c, "total": round(t, 2)} for c, t in totals.items()]
    return sorted(rows, key=lambda r: (-r["total"], r["category"]))


def spent_in_month(purchases: list[dict], month: str) -> float:
    return round(sum(p["total"] for p in purchases if p["purchased_on"][:7] == month), 2)


def budget_status(monthly_budget: float, spent: float, month: str) -> dict:
    return {
        "month": month,
        "monthly": round(monthly_budget, 2),
        "spent": round(spent, 2),
        "remaining": round(monthly_budget - spent, 2),
        "used_pct": round(100 * spent / monthly_budget) if monthly_budget > 0 else 0,
        "over_budget": spent > monthly_budget,
    }


def excess_stock(views: list[dict], threshold_days: float = EXCESS_DAYS) -> dict:
    """Stock beyond threshold_days of cover, and the money tied up in it."""
    items = []
    for v in views:
        days = v["days_left"]
        if days is None or days <= threshold_days:
            continue
        qty = v["stock"] - v["daily_usage"] * threshold_days
        items.append(
            {
                "item": v["item"],
                "unit": v["unit"],
                "stock": v["stock"],
                "unit_cost": v["unit_cost"],
                "days_left": round(days, 1),
                "excess_qty": round(qty, 1),
                "excess_value": round(qty * v["unit_cost"], 2),
            }
        )
    items.sort(key=lambda i: -i["excess_value"])
    return {
        "threshold_days": threshold_days,
        "value": round(sum(i["excess_value"] for i in items), 2),
        "items": items,
    }
