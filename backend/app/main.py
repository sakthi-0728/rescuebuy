import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import date

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app import db
from app.ai import explain_recommendation, explain_scenarios
from app.assistant import answer_question
from app.analytics import (
    budget_status, excess_stock, last_months, monthly_spend, spend_by_category, spent_in_month,
)
from app.compare import evaluate_suppliers, option_facts, plan_order
from app.inventory import build_alerts, item_view, summarize
from app.lab import (
    build_candidates, cheapest, comparison_savings, recommended_key, simulate,
)
from app.orders import (
    Order, Status, add_event, approve, authorization_state, mark_authorized,
    mark_delivered, reject, restart_payment, start_payment,
)
from app.snapshot import build_views, load_snapshot
from app.paypal import (
    authorize_paypal_order, capture_authorization, create_paypal_order,
    verify_webhook_signature,
)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="RescueBuy", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


class OrderRequest(BaseModel):
    item: str
    supplier: str | None = None


def not_found(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what} not found")


def load_context(conn, item_name: str):
    """Everything the planner needs, read from the database (never from the browser)."""
    item = db.get_item(conn, item_name)
    if item is None:
        raise not_found("Item")
    suppliers = db.load_offers(conn, item_name)
    policy = db.load_policy(conn)
    buffer_days = db.get_settings(conn)["buffer_days"]
    return item, suppliers, policy, buffer_days


def load_order(order_id: int) -> Order:
    with db.connect() as conn:
        order = db.get_order(conn, order_id)
    if order is None:
        raise not_found("Order")
    return order


def apply_transition(order_id: int, transition) -> dict:
    """Load an order, apply a state change, save it. Illegal changes become 409."""
    with db.connect() as conn:
        order = db.get_order(conn, order_id)
        if order is None:
            raise not_found("Order")
        try:
            transition(order)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        db.save_order(conn, order)
    return asdict(order)


@app.get("/health")
def health():
    return {"status": "ok"}


# ---- Inventory and alerts ----

@app.get("/items")
def read_items():
    with db.connect() as conn:
        return build_views(conn)


@app.get("/dashboard")
def read_dashboard():
    with db.connect() as conn:
        views = build_views(conn)
        open_orders = db.count_open_orders(conn)
        purchases = db.load_purchases(conn)
        settings = db.get_settings(conn)
    alerts = build_alerts(views)
    summary = summarize(views, alerts, open_orders)
    summary["budget_remaining"] = budget_now(purchases, settings)["remaining"]
    return {
        "demo_data": True,
        "summary": summary,
        "attention": alerts,
    }


@app.get("/stock")
def read_stock():
    with db.connect() as conn:
        return {i.name: i.stock for i in db.load_items(conn)}


# ---- Recommendation ----

@app.post("/recommend")
def get_recommendation(req: OrderRequest):
    with db.connect() as conn:
        item, suppliers, policy, buffer_days = load_context(conn, req.item)

    plan = plan_order(item.stock, item.incoming, item.daily_usage, suppliers, policy, buffer_days)
    chosen = plan.choice.option if plan.choice else None

    facts = {
        "item": item.name,
        "days_left": plan.days_left,
        "risk": plan.risk,
        "supplier": chosen.supplier.name if chosen else None,
        "qty": chosen.qty if chosen else 0,
        "total": chosen.total if chosen else 0.0,
        "needs_approval": bool(chosen and chosen.policy.needs_approval),
    }
    return {
        "item": item.name,
        "days_left": plan.days_left,
        "risk": plan.risk,
        "message": plan.message,
        "options": [{**option_facts(o), "chosen": o is chosen} for o in plan.options],
        "rejected": [asdict(r) for r in plan.rejected],
        "choice": (
            {
                "supplier": chosen.supplier.name,
                "reason": plan.choice.reason,
                "source": plan.choice.source,
            }
            if chosen
            else None
        ),
        "explanation": explain_recommendation(facts),
    }


# ---- Orders ----

@app.post("/orders")
def create_order(req: OrderRequest):
    with db.connect() as conn:
        item, suppliers, policy, buffer_days = load_context(conn, req.item)
        existing = db.open_order_for_item(conn, item.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Order {existing.id} for {item.name} is already in progress",
        )

    if req.supplier:
        options, _ = evaluate_suppliers(
            item.stock, item.incoming, item.daily_usage, suppliers, policy, buffer_days
        )
        option = next((o for o in options if o.supplier.name == req.supplier), None)
        if option is None:
            raise HTTPException(
                status_code=400, detail=f"{req.supplier} is not an eligible option"
            )
    else:
        plan = plan_order(
            item.stock, item.incoming, item.daily_usage, suppliers, policy, buffer_days
        )
        if plan.choice is None:
            raise HTTPException(status_code=400, detail=plan.message)
        option = plan.choice.option

    with db.connect() as conn:
        order = db.create_order(conn, item.name, option.supplier.name, option.qty, option.total)
    return asdict(order)


@app.get("/orders")
def list_orders():
    with db.connect() as conn:
        return [asdict(o) for o in db.list_orders(conn)]


@app.get("/orders/{order_id}")
def read_order(order_id: int):
    return asdict(load_order(order_id))


@app.post("/orders/{order_id}/approve")
def approve_order(order_id: int):
    return apply_transition(order_id, approve)


@app.post("/orders/{order_id}/reject")
def reject_order(order_id: int):
    return apply_transition(order_id, reject)


@app.post("/orders/{order_id}/restart-payment")
def restart_order_payment(order_id: int):
    return apply_transition(order_id, restart_payment)


@app.post("/orders/{order_id}/pay")
def pay_order(order_id: int):
    order = load_order(order_id)
    if order.status != Status.APPROVED:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot pay for an order that is {order.status.value}",
        )
    try:
        paypal_order = create_paypal_order(order.total, f"RescueBuy order {order.id}")
    except Exception:
        raise HTTPException(status_code=502, detail="PayPal request failed")

    saved = apply_transition(order_id, lambda o: start_payment(o, paypal_order["id"]))
    approval_url = next(
        (l["href"] for l in paypal_order["links"] if l["rel"] == "payer-action"),
        None,
    )
    return {"order": saved, "approval_url": approval_url}


@app.get("/paypal/return")
def paypal_return(token: str):
    """PayPal sends the buyer here after approval. `token` is the PayPal order id."""
    with db.connect() as conn:
        order = db.find_order_by_paypal_id(conn, token)
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

    apply_transition(order.id, lambda o: mark_authorized(o, authorization_id))
    return RedirectResponse(
        f"{FRONTEND_URL}/?payment=authorized&order={order.id}", status_code=303
    )


@app.get("/paypal/cancel")
def paypal_cancel():
    return RedirectResponse(f"{FRONTEND_URL}/?payment=cancelled", status_code=303)


@app.post("/orders/{order_id}/confirm-delivery")
def confirm_delivery(order_id: int):
    order = load_order(order_id)
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

    # Stock changes only here, after the capture, in one database transaction.
    with db.connect() as conn:
        order = db.get_order(conn, order_id)
        try:
            mark_delivered(order, capture_id)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        db.add_stock(conn, order.item, order.qty)
        db.record_purchase(conn, order.item, order.supplier_name, order.qty, order.total)
        add_event(order, "STOCK_UPDATED", f"Added {order.qty} to {order.item} stock")
        db.save_order(conn, order)
    return {"message": "Delivery confirmed. Payment captured.", "order": asdict(order)}


# ---- Budget, analytics and the Decision Lab ----

def budget_now(purchases: list[dict], settings: dict) -> dict:
    month = last_months(date.today(), 1)[0]
    return budget_status(settings["monthly_budget"], spent_in_month(purchases, month), month)


def planning_inputs(conn):
    items = db.load_items(conn)
    offers = {i.name: db.load_offers(conn, i.name) for i in items}
    policy = db.load_policy(conn)
    buffer_days = db.get_settings(conn)["buffer_days"]
    return items, offers, policy, buffer_days


@app.get("/analytics")
def read_analytics(months: int = Query(default=6, ge=1, le=12)):
    with db.connect() as conn:
        purchases = db.load_purchases(conn)
        settings = db.get_settings(conn)
        views = build_views(conn)
        items, offers, policy, buffer_days = planning_inputs(conn)

    window = last_months(date.today(), months)
    budget = budget_now(purchases, settings)
    candidates, _ = build_candidates(items, offers, policy, buffer_days)
    upcoming = [(c.item, cheapest(c)) for c in candidates]
    upcoming_cost = round(sum(o.total for _, o in upcoming), 2)
    return {
        "demo_data": True,
        "months": months,
        "budget": budget,
        "monthly_spend": monthly_spend(purchases, window),
        "by_category": spend_by_category(purchases, window),
        "upcoming": {
            "cost": upcoming_cost,
            "vs_remaining": round(budget["remaining"] - upcoming_cost, 2),
            "basis": "Every item that needs a reorder, from the supplier with the lowest total cost.",
            "items": [
                {"item": name, "supplier": o.supplier.name, "qty": o.qty, "total": o.total}
                for name, o in upcoming
            ],
        },
        "excess": excess_stock(views),
        "savings": comparison_savings(candidates),
    }


class LabRequest(BaseModel):
    budget: float | None = Field(default=None, ge=0, le=1_000_000)
    supplier_delay_days: float = Field(default=0, ge=0, le=14)
    wait_days: float = Field(default=2, ge=0, le=14)


class LabOrdersRequest(LabRequest):
    scenario: str


def run_lab(req: LabRequest):
    with db.connect() as conn:
        settings = db.get_settings(conn)
        purchases = db.load_purchases(conn)
        items, offers, policy, buffer_days = planning_inputs(conn)
    budget = req.budget if req.budget is not None else max(0.0, budget_now(purchases, settings)["remaining"])
    candidates, unfillable = build_candidates(items, offers, policy, buffer_days)
    results = simulate(candidates, budget, req.supplier_delay_days, req.wait_days)
    return budget, results, unfillable


@app.post("/lab/simulate")
def lab_simulate(req: LabRequest):
    """Read-only: nothing is ordered, charged or changed."""
    budget, results, unfillable = run_lab(req)
    recommended = recommended_key(results)
    facts = {
        "budget": budget,
        "supplier_delay_days": req.supplier_delay_days,
        "wait_days": req.wait_days,
        "recommended": recommended,
        "scenarios": [
            {
                "key": r.key,
                "name": r.name,
                "spend": r.spend,
                "budget_remaining": r.budget_remaining,
                "over_budget": r.over_budget,
                "bought": [line.item for line in r.bought],
                "deferred": [d.item for d in r.deferred],
                "exposed": r.exposed,
            }
            for r in results
        ],
    }
    return {
        "inputs": {
            "budget": budget,
            "supplier_delay_days": req.supplier_delay_days,
            "wait_days": req.wait_days,
        },
        "estimate_note": "Estimates based on current usage and supplier lead times, not guarantees.",
        "baseline": "Savings compare each strategy with buying everything now from the fastest suppliers.",
        "scenarios": [asdict(r) for r in results],
        "recommended": recommended,
        "unfillable": unfillable,
        "explanation": explain_scenarios(facts),
    }


@app.post("/lab/orders")
def lab_create_orders(req: LabOrdersRequest):
    """Turn a scenario into proposed orders. They still wait for the owner's approval."""
    _, results, _ = run_lab(req)
    scenario = next((r for r in results if r.key == req.scenario), None)
    if scenario is None:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {req.scenario}")
    if not scenario.bought:
        raise HTTPException(status_code=400, detail="This scenario buys nothing today.")

    created, skipped = [], []
    with db.connect() as conn:
        for line in scenario.bought:
            existing = db.open_order_for_item(conn, line.item)
            if existing:
                skipped.append({"item": line.item, "reason": f"Order {existing.id} is already in progress"})
                continue
            order = db.create_order(conn, line.item, line.supplier, line.qty, line.total)
            created.append(asdict(order))
    return {"scenario": scenario.name, "created": created, "skipped": skipped}


# ---- Ask Rescue AI ----

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@app.post("/assistant/ask")
def assistant_ask(req: AskRequest):
    """Read-only: answers from the database. It cannot order, approve or pay."""
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="Ask a question.")
    with db.connect() as conn:
        snapshot = load_snapshot(conn)
    return answer_question(req.question, snapshot)


# ---- Webhooks ----

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

    with db.connect() as conn:
        is_new = db.record_webhook_event(
            conn, event["id"], event.get("event_type"), event.get("summary")
        )
    return {"status": "received" if is_new else "duplicate"}


@app.get("/events")
def read_events():
    with db.connect() as conn:
        return db.list_webhook_events(conn)


# ---- Demo ----

@app.post("/demo/reset")
def reset_demo():
    if not DEMO_MODE:
        raise HTTPException(status_code=403, detail="Demo reset is disabled")
    db.init_db(force=True)
    return {"status": "reset"}
