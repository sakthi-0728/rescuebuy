import os

from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from app.forecast import days_left, risk_level

from app.orders import (
    Order, Status, add_event, approve, authorization_state, mark_authorized,
    mark_delivered, reject, start_payment,
)

from app.paypal import (
    authorize_paypal_order, capture_authorization, create_paypal_order,
    verify_webhook_signature,
)
from app.policy import Policy
from app.compare import build_options, option_facts, plan_order
from app.suppliers import Supplier
from app.ai import explain_recommendation

app = FastAPI(title="RescueBuy")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

POLICY = Policy(max_auto_spend=500, budget=2000)

SUPPLIERS = [
    Supplier("Pricey", unit_price=3, lead_time_days=1, reliability=0.98),
    Supplier("Acme", unit_price=2, lead_time_days=2, reliability=0.95),
    Supplier("Slowco", unit_price=1, lead_time_days=5, reliability=0.80),
]

ORDERS: dict[int, Order] = {}
INITIAL_STOCK = {"boxes": 600, "flour": 900, "butter": 10}
STOCK: dict[str, int] = dict(INITIAL_STOCK)
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

ITEMS: dict[str, dict] = {
    "boxes": {"unit": "boxes", "daily_usage": 200, "incoming": 0},
    "flour": {"unit": "kg", "daily_usage": 30, "incoming": 0},
    "butter": {"unit": "kg", "daily_usage": 10, "incoming": 0},
}
EVENTS: list[dict] = []
SEEN_EVENT_IDS: set[str] = set()


class RecommendRequest(BaseModel):
    stock: float
    incoming: float = 0
    daily_usage: float
    buffer_days: float = 2
    item: str = "boxes"
    supplier: str | None = None


def get_order(order_id: int) -> Order:
    order = ORDERS.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/recommend")
def get_recommendation(req: RecommendRequest):
    plan = plan_order(
        req.stock, req.incoming, req.daily_usage,
        SUPPLIERS, POLICY, buffer_days=req.buffer_days,
    )
    chosen = plan.choice.option if plan.choice else None
    data = {
        "days_left": plan.days_left,
        "risk": plan.risk,
        "supplier": asdict(chosen.supplier) if chosen else None,
        "qty": chosen.qty if chosen else 0,
        "total": chosen.total if chosen else 0.0,
        "policy": asdict(chosen.policy) if chosen else None,
        "message": plan.message,
        "options": [{**option_facts(o), "chosen": o is chosen} for o in plan.options],
        "choice": (
            {
                "supplier": chosen.supplier.name,
                "reason": plan.choice.reason,
                "source": plan.choice.source,
            }
            if chosen
            else None
        ),
    }
    facts = {
        "item": req.item,
        "days_left": plan.days_left,
        "risk": plan.risk,
        "supplier": chosen.supplier.name if chosen else None,
        "qty": chosen.qty if chosen else 0,
        "total": chosen.total if chosen else 0.0,
        "needs_approval": bool(chosen and chosen.policy.needs_approval),
    }
    data["explanation"] = explain_recommendation(facts)
    return data

@app.post("/orders")
def create_order(req: RecommendRequest):
    if req.supplier:
        options = build_options(
            req.stock, req.incoming, req.daily_usage,
            SUPPLIERS, POLICY, buffer_days=req.buffer_days,
        )
        option = next((o for o in options if o.supplier.name == req.supplier), None)
        if option is None:
            raise HTTPException(
                status_code=400,
                detail=f"{req.supplier} is not an eligible option",
            )
    else:
        plan = plan_order(
            req.stock, req.incoming, req.daily_usage,
            SUPPLIERS, POLICY, buffer_days=req.buffer_days,
        )
        if plan.choice is None:
            raise HTTPException(status_code=400, detail=plan.message)
        option = plan.choice.option

    order = Order(
        id=len(ORDERS) + 1,
        supplier_name=option.supplier.name,
        qty=option.qty,
        total=option.total,
        item=req.item,
    )
    ORDERS[order.id] = order
    return asdict(order)

@app.get("/orders/{order_id}")
def read_order(order_id: int):
    return asdict(get_order(order_id))


@app.post("/orders/{order_id}/approve")
def approve_order(order_id: int):
    try:
        return asdict(approve(get_order(order_id)))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.post("/orders/{order_id}/reject")
def reject_order(order_id: int):
    try:
        return asdict(reject(get_order(order_id)))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

@app.post("/orders/{order_id}/pay")
def pay_order(order_id: int):
    order = get_order(order_id)
    if order.status != Status.APPROVED:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot pay for an order that is {order.status.value}",
        )
    try:
        paypal_order = create_paypal_order(order.total, f"RescueBuy order {order.id}")
    except Exception:
        raise HTTPException(status_code=502, detail="PayPal request failed")
    start_payment(order, paypal_order["id"])
    approval_url = next(
        (l["href"] for l in paypal_order["links"] if l["rel"] == "payer-action"),
        None,
    )
    return {"order": asdict(order), "approval_url": approval_url}

@app.get("/paypal/return")
def paypal_return(token: str):
    """PayPal sends the buyer here after approval. `token` is the PayPal order id."""
    order = next((o for o in ORDERS.values() if o.paypal_order_id == token), None)
    if order is None:
        raise HTTPException(status_code=404, detail="No order matches this payment")
    if order.status != Status.PAYMENT_STARTED:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot authorize an order that is {order.status.value}",
        )
    try:
        result = authorize_paypal_order(token)
        authorization_id = result["purchase_units"][0]["payments"]["authorizations"][0]["id"]
    except Exception:
        raise HTTPException(status_code=502, detail="PayPal authorization failed")
    mark_authorized(order, authorization_id)
    return RedirectResponse(
        f"{FRONTEND_URL}/?payment=authorized&order={order.id}", status_code=303
    )


@app.get("/paypal/cancel")
def paypal_cancel():
    return RedirectResponse(f"{FRONTEND_URL}/?payment=cancelled", status_code=303)

@app.post("/orders/{order_id}/confirm-delivery")
def confirm_delivery(order_id: int):
    order = get_order(order_id)
    if order.status != Status.AUTHORIZED:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot confirm delivery of an order that is {order.status.value}",
        )

    state = authorization_state(order)
    if state == "expired":
        raise HTTPException(
            status_code=409,
            detail="The payment authorization has expired. A new payment is needed.",
        )

    try:
        result = capture_authorization(order.authorization_id)
        if result.get("status") != "COMPLETED":
            raise RuntimeError("Capture not completed")
        capture_id = result["id"]
    except Exception:
        detail = "PayPal capture failed"
        if state == "past_honor":
            detail += ". The authorization is older than 3 days and may have expired."
        raise HTTPException(status_code=502, detail=detail)

    mark_delivered(order, capture_id)
    STOCK[order.item] = STOCK.get(order.item, 0) + order.qty
    add_event(order, "STOCK_UPDATED", f"Added {order.qty} {order.item} to stock")
    return {"message": "Delivery confirmed. Payment captured.", "order": asdict(order)}

@app.get("/stock")
def read_stock():
    return STOCK

@app.post("/webhooks/paypal")
async def paypal_webhook(request: Request):
    try:
        event = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Body must be valid JSON")
    if not isinstance(event, dict) or not event.get("id"):
        raise HTTPException(status_code=400, detail="Missing event id")

    try:
        verified = verify_webhook_signature(request.headers, event)
    except Exception:
        verified = False
    if not verified:
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event_id = event["id"]
    if event_id in SEEN_EVENT_IDS:
        return {"status": "duplicate"}

    SEEN_EVENT_IDS.add(event_id)
    EVENTS.append(
        {
            "id": event_id,
            "type": event.get("event_type"),
            "summary": event.get("summary"),
        }
    )
    return {"status": "received"}


@app.get("/events")
def read_events():
    return EVENTS

@app.get("/items")
def read_items():
    lead = min(s.lead_time_days for s in SUPPLIERS if s.approved)
    rows = []
    for name, info in ITEMS.items():
        stock = STOCK.get(name, 0)
        days = days_left(stock, info["incoming"], info["daily_usage"])
        rows.append(
            {
                "item": name,
                "unit": info["unit"],
                "stock": stock,
                "daily_usage": info["daily_usage"],
                "incoming": info["incoming"],
                "days_left": days,
                "risk": risk_level(days, lead),
            }
        )
    return rows


@app.get("/orders")
def list_orders():
    return [asdict(o) for o in ORDERS.values()]

@app.post("/demo/reset")
def reset_demo():
    if not DEMO_MODE:
        raise HTTPException(status_code=403, detail="Demo reset is disabled")
    ORDERS.clear()
    EVENTS.clear()
    SEEN_EVENT_IDS.clear()
    STOCK.clear()
    STOCK.update(INITIAL_STOCK)
    return {"status": "reset"}