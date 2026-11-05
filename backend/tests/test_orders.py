from datetime import datetime, timedelta, timezone

import pytest

from app.orders import (
    Order,
    Status,
    approve,
    authorization_state,
    mark_authorized,
    mark_delivered,
    reject,
    restart_payment,
    start_payment,
)


def make_order():
    return Order(id=1, supplier_name="Acme", qty=400, total=800.0)


def test_new_order_waits_for_approval():
    assert make_order().status == Status.PENDING_APPROVAL


def test_approve_pending_order():
    order = approve(make_order())
    assert order.status == Status.APPROVED


def test_reject_pending_order():
    order = reject(make_order())
    assert order.status == Status.REJECTED


def test_cannot_approve_twice():
    order = approve(make_order())
    with pytest.raises(ValueError):
        approve(order)


def test_cannot_approve_rejected_order():
    order = reject(make_order())
    with pytest.raises(ValueError):
        approve(order)


def test_start_payment_on_approved_order():
    order = start_payment(approve(make_order()), "PP123")
    assert order.status == Status.PAYMENT_STARTED
    assert order.paypal_order_id == "PP123"


def test_cannot_pay_for_unapproved_order():
    with pytest.raises(ValueError):
        start_payment(make_order(), "PP123")


def test_mark_authorized_after_payment_started():
    order = start_payment(approve(make_order()), "PP123")
    mark_authorized(order, "AUTH1")
    assert order.status == Status.AUTHORIZED
    assert order.authorization_id == "AUTH1"


def test_cannot_authorize_before_payment_started():
    with pytest.raises(ValueError):
        mark_authorized(approve(make_order()), "AUTH1")


def make_authorized_order():
    order = start_payment(approve(make_order()), "PP123")
    return mark_authorized(order, "AUTH1")


def test_mark_delivered_after_authorized():
    order = mark_delivered(make_authorized_order(), "CAP1")
    assert order.status == Status.DELIVERED_CAPTURED
    assert order.capture_id == "CAP1"


def test_cannot_deliver_before_authorized():
    with pytest.raises(ValueError):
        mark_delivered(approve(make_order()), "CAP1")


def test_new_order_has_created_event():
    order = make_order()
    assert [e["type"] for e in order.timeline] == ["ORDER_CREATED"]


def test_full_flow_timeline():
    order = make_order()
    approve(order)
    start_payment(order, "PP123")
    mark_authorized(order, "AUTH1")
    mark_delivered(order, "CAP1")
    assert [e["type"] for e in order.timeline] == [
        "ORDER_CREATED",
        "APPROVED",
        "PAYMENT_STARTED",
        "AUTHORIZED",
        "DELIVERED_CAPTURED",
    ]


def test_failed_transition_adds_no_event():
    order = approve(make_order())
    with pytest.raises(ValueError):
        mark_authorized(order, "AUTH1")
    assert [e["type"] for e in order.timeline] == ["ORDER_CREATED", "APPROVED"]


def test_events_have_timestamps():
    order = approve(make_order())
    assert all("T" in e["time"] for e in order.timeline)


def days_ago(days):
    return datetime.now(timezone.utc) - timedelta(days=days)


def test_authorized_at_is_recorded():
    assert make_authorized_order().authorized_at is not None


def test_unauthorized_order_has_no_state():
    assert authorization_state(make_order()) is None


def test_fresh_authorization():
    order = start_payment(approve(make_order()), "PP1")
    mark_authorized(order, "A1", now=days_ago(1))
    assert authorization_state(order) == "fresh"


def test_authorization_past_honor_period():
    order = start_payment(approve(make_order()), "PP1")
    mark_authorized(order, "A1", now=days_ago(5))
    assert authorization_state(order) == "past_honor"


def test_authorization_expired():
    order = start_payment(approve(make_order()), "PP1")
    mark_authorized(order, "A1", now=days_ago(30))
    assert authorization_state(order) == "expired"


def test_restart_payment_returns_to_approved():
    order = start_payment(approve(make_order()), "PP123")
    restart_payment(order)
    assert order.status == Status.APPROVED
    assert order.paypal_order_id is None
    assert order.timeline[-1]["type"] == "PAYMENT_RESTARTED"


def test_cannot_restart_payment_unless_it_was_started():
    with pytest.raises(ValueError):
        restart_payment(approve(make_order()))


def test_cannot_restart_payment_once_authorized():
    with pytest.raises(ValueError):
        restart_payment(make_authorized_order())
