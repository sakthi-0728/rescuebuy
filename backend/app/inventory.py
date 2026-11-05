from dataclasses import dataclass
from datetime import date

from app.forecast import days_left, risk_level

EXPIRY_ALERT_DAYS = 3         # always alert when something expires this soon
EXPIRY_WASTE_WINDOW_DAYS = 7  # alert earlier if stock would go unused before expiry


@dataclass
class Item:
    name: str
    category: str
    unit: str
    stock: float
    daily_usage: float
    incoming: float
    unit_cost: float
    criticality: int = 2          # 1 = nice to have, 3 = the business stops without it
    expiry_date: str | None = None  # only set for perishables
    last_restocked: str | None = None


def days_until(expiry_date: str | None, today: date) -> int | None:
    """Whole days from today until the date. None when there is no expiry data."""
    if not expiry_date:
        return None
    return (date.fromisoformat(expiry_date) - today).days


def expiring_unused(stock: float, daily_usage: float, days_to_expiry: int | None) -> float:
    """Quantity that would still be on hand at expiry at the current usage rate."""
    if days_to_expiry is None:
        return 0.0
    if days_to_expiry < 0:
        return stock
    return max(0.0, stock - daily_usage * days_to_expiry)


def item_view(
    item: Item, lead_time_days: float | None, buffer_days: float, today: date
) -> dict:
    days = days_left(item.stock, item.incoming, item.daily_usage)
    dte = days_until(item.expiry_date, today)
    return {
        "item": item.name,
        "category": item.category,
        "unit": item.unit,
        "stock": item.stock,
        "daily_usage": item.daily_usage,
        "incoming": item.incoming,
        "unit_cost": item.unit_cost,
        "inventory_value": round(item.stock * item.unit_cost, 2),
        "criticality": item.criticality,
        "days_left": days,
        "risk": risk_level(days, lead_time_days or 0, buffer_days),
        "fastest_lead_time_days": lead_time_days,
        "expiry_date": item.expiry_date,
        "days_to_expiry": dte,
        "expiring_unused": round(expiring_unused(item.stock, item.daily_usage, dte), 1),
        "last_restocked": item.last_restocked,
    }


def _plural(n: float, word: str) -> str:
    return f"{n:g} {word}" if n == 1 else f"{n:g} {word}s"


def build_alerts(views: list[dict]) -> list[dict]:
    """Stockout and expiry alerts, most urgent first. Expiry alerts need real expiry data."""
    alerts = []
    for v in views:
        name, unit = v["item"], v["unit"]

        if v["risk"] in ("critical", "warning"):
            days = v["days_left"]
            lead = v["fastest_lead_time_days"]
            if lead is None:
                reason = f"About {_plural(round(days, 1), 'day')} of stock left and no approved supplier offers it."
            elif v["risk"] == "critical":
                reason = (
                    f"About {_plural(round(days, 1), 'day')} of stock left. The fastest supplier needs "
                    f"{_plural(lead, 'day')}, so there is no margin."
                )
            else:
                reason = (
                    f"About {_plural(round(days, 1), 'day')} of stock left. The fastest supplier needs "
                    f"{_plural(lead, 'day')}."
                )
            alerts.append(
                {
                    "item": name,
                    "kind": "stockout",
                    "severity": v["risk"],
                    "title": f"{name} is running low",
                    "reason": reason,
                    "action": "review_reorder",
                    "days_left": days,
                    "criticality": v["criticality"],
                    "open_order": v.get("open_order"),
                }
            )

        dte = v["days_to_expiry"]
        if dte is not None:
            unused = v["expiring_unused"]
            if dte < 0:
                severity = "critical"
                reason = f"Expired {_plural(-dte, 'day')} ago. Remove {v['stock']:g} {unit} from stock."
            elif dte <= EXPIRY_ALERT_DAYS or (dte <= EXPIRY_WASTE_WINDOW_DAYS and unused > 0):
                severity = "critical" if dte <= 1 else "warning"
                when = "today" if dte == 0 else f"in {_plural(dte, 'day')}"
                tail = (
                    f" At the current usage about {unused:g} {unit} may go unused."
                    if unused > 0
                    else " At the current usage it should be used in time."
                )
                reason = f"Expires {when}.{tail}"
            else:
                continue
            alerts.append(
                {
                    "item": name,
                    "kind": "expiry",
                    "severity": severity,
                    "title": f"{name} expires soon" if dte >= 0 else f"{name} has expired",
                    "reason": reason,
                    "action": None,
                    "days_left": v["days_left"],
                    "criticality": v["criticality"],
                    "open_order": v.get("open_order"),
                }
            )

    def sort_key(a: dict):
        days = a["days_left"] if a["days_left"] is not None else float("inf")
        return (
            0 if a["severity"] == "critical" else 1,
            0 if a["kind"] == "stockout" else 1,
            -a["criticality"],
            days,
        )

    return sorted(alerts, key=sort_key)


def summarize(views: list[dict], alerts: list[dict], open_orders: int) -> dict:
    return {
        "item_count": len(views),
        "inventory_value": round(sum(v["inventory_value"] for v in views), 2),
        "critical_count": sum(1 for v in views if v["risk"] == "critical"),
        "low_count": sum(1 for v in views if v["risk"] == "warning"),
        "expiry_alerts": sum(1 for a in alerts if a["kind"] == "expiry"),
        "open_orders": open_orders,
    }
