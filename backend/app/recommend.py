from dataclasses import dataclass

from app.forecast import days_left, reorder_qty, risk_level
from app.policy import Policy, PolicyResult, check_order
from app.suppliers import Supplier, best_supplier


@dataclass
class Recommendation:
    days_left: float | None
    risk: str
    supplier: Supplier | None
    qty: int
    total: float
    policy: PolicyResult | None
    message: str


def recommend(
    stock: float,
    incoming: float,
    daily_usage: float,
    suppliers: list[Supplier],
    policy: Policy,
    buffer_days: float = 2,
) -> Recommendation:
    days = days_left(stock, incoming, daily_usage)

    supplier = best_supplier(suppliers, days)
    if supplier is None:
        # Nobody qualifies. Use the fastest approved lead time just to report risk.
        approved = [s for s in suppliers if s.approved]
        lead = min((s.lead_time_days for s in approved), default=0)
        return Recommendation(
            days, risk_level(days, lead, buffer_days), None, 0, 0.0, None,
            "No eligible supplier. Escalate to the owner.",
        )

    qty = reorder_qty(
        stock, incoming, daily_usage, supplier.lead_time_days, buffer_days,
        unit_price=supplier.unit_price, budget=policy.budget,
    )
    risk = risk_level(days, supplier.lead_time_days, buffer_days)

    if qty == 0:
        return Recommendation(days, risk, supplier, 0, 0.0, None, "Stock is sufficient. No order needed.")

    total = supplier.unit_price * qty + supplier.delivery_fee
    result = check_order(supplier, qty, policy)
    return Recommendation(days, risk, supplier, qty, total, result, "Order recommended.")
