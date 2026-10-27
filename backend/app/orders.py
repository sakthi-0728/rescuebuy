from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


class Status(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PAYMENT_STARTED = "PAYMENT_STARTED"
    AUTHORIZED = "AUTHORIZED"
    DELIVERED_CAPTURED = "DELIVERED_CAPTURED"


@dataclass
class Order:
    id: int
    supplier_name: str
    qty: int
    total: float
    status: Status = Status.PENDING_APPROVAL
    paypal_order_id: str | None = None
    authorization_id: str | None = None
    capture_id: str | None = None
    item: str = "boxes"
    timeline: list[dict] = field(default_factory=list)
    authorized_at: str | None = None

    def __post_init__(self):
        if not self.timeline:
            add_event(
                self,
                "ORDER_CREATED",
                f"{self.qty} {self.item} from {self.supplier_name}, ${self.total:.2f}",
            )


def add_event(order: Order, event_type: str, detail: str) -> None:
    order.timeline.append(
        {
            "type": event_type,
            "detail": detail,
            "time": datetime.now(timezone.utc).isoformat(),
        }
    )

HONOR_DAYS = 3
VALID_DAYS = 29


def authorization_state(order: Order, now: datetime | None = None) -> str | None:
    """None (never authorized), 'fresh', 'past_honor' or 'expired'."""
    if order.authorized_at is None:
        return None
    now = now or datetime.now(timezone.utc)
    age = now - datetime.fromisoformat(order.authorized_at)
    if age > timedelta(days=VALID_DAYS):
        return "expired"
    if age > timedelta(days=HONOR_DAYS):
        return "past_honor"
    return "fresh"

def approve(order: Order) -> Order:
    if order.status != Status.PENDING_APPROVAL:
        raise ValueError(f"Cannot approve an order that is {order.status.value}")
    order.status = Status.APPROVED
    add_event(order, "APPROVED", "Owner approved the order")
    return order


def reject(order: Order) -> Order:
    if order.status != Status.PENDING_APPROVAL:
        raise ValueError(f"Cannot reject an order that is {order.status.value}")
    order.status = Status.REJECTED
    add_event(order, "REJECTED", "Owner rejected the order")
    return order


def start_payment(order: Order, paypal_order_id: str) -> Order:
    if order.status != Status.APPROVED:
        raise ValueError(f"Cannot pay for an order that is {order.status.value}")
    order.status = Status.PAYMENT_STARTED
    order.paypal_order_id = paypal_order_id
    add_event(order, "PAYMENT_STARTED", "PayPal order created, waiting for buyer approval")
    return order


def mark_authorized(
    order: Order, authorization_id: str, now: datetime | None = None
) -> Order:
    if order.status != Status.PAYMENT_STARTED:
        raise ValueError(f"Cannot authorize an order that is {order.status.value}")
    order.status = Status.AUTHORIZED
    order.authorization_id = authorization_id
    order.authorized_at = (now or datetime.now(timezone.utc)).isoformat()
    add_event(order, "AUTHORIZED", "Funds reserved, not charged")
    return order


def mark_delivered(order: Order, capture_id: str) -> Order:
    if order.status != Status.AUTHORIZED:
        raise ValueError(f"Cannot confirm delivery of an order that is {order.status.value}")
    order.status = Status.DELIVERED_CAPTURED
    order.capture_id = capture_id
    add_event(order, "DELIVERED_CAPTURED", "Delivery confirmed, payment captured")
    return order