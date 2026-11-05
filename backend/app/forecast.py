import math


def days_left(stock: float, incoming: float, daily_usage: float) -> float | None:
    """Days until stock runs out. None means no usage, so it never runs out."""
    if daily_usage <= 0:
        return None
    return (stock + incoming) / daily_usage


def risk_level(days: float | None, lead_time_days: float, buffer_days: float = 2) -> str:
    """critical: runs out before a new order could arrive."""
    if days is None:
        return "ok"
    if days <= lead_time_days:
        return "critical"
    if days <= lead_time_days + buffer_days:
        return "warning"
    return "ok"


def reorder_qty(
    stock: float,
    incoming: float,
    daily_usage: float,
    lead_time_days: float,
    buffer_days: float = 2,
    unit_price: float | None = None,
    budget: float | None = None,
) -> int:
    """Units needed to cover demand over (lead time + buffer), capped by budget."""
    target = daily_usage * (lead_time_days + buffer_days)
    qty = max(0, math.ceil(target - stock - incoming))
    if budget is not None and unit_price:
        qty = min(qty, math.floor(budget / unit_price))
    return qty
