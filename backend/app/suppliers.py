from dataclasses import dataclass


@dataclass
class Supplier:
    name: str
    unit_price: float
    lead_time_days: float
    approved: bool = True
    stock_available: int | None = None  # None = no limit known
    reliability: float | None = None    # share of on-time deliveries; None = unknown
    min_order_qty: int = 1
    delivery_fee: float = 0.0
    history_count: int = 0              # deliveries on record behind the reliability


def arrives_in_time(supplier: Supplier, days_of_stock_left: float | None) -> bool:
    """True if the supplier delivers before stock runs out."""
    if days_of_stock_left is None:
        return True
    return supplier.lead_time_days <= days_of_stock_left


def eligible_suppliers(
    suppliers: list[Supplier], days_of_stock_left: float | None
) -> list[Supplier]:
    """Only approved suppliers that arrive before stock runs out."""
    return [
        s for s in suppliers
        if s.approved and arrives_in_time(s, days_of_stock_left)
    ]


def best_supplier(
    suppliers: list[Supplier], days_of_stock_left: float | None
) -> Supplier | None:
    """Cheapest eligible supplier; faster delivery wins a price tie. None if no one qualifies."""
    candidates = eligible_suppliers(suppliers, days_of_stock_left)
    if not candidates:
        return None
    return min(candidates, key=lambda s: (s.unit_price, s.lead_time_days))
