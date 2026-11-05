from dataclasses import dataclass

from app.ai import choose_supplier
from app.forecast import days_left, reorder_qty, risk_level
from app.policy import Policy, PolicyResult, check_order
from app.recommend import recommend
from app.suppliers import Supplier, arrives_in_time


@dataclass
class Option:
    supplier: Supplier
    qty: int
    total: float  # unit price x quantity + delivery fee
    policy: PolicyResult
    note: str | None = None
    margin_days: float | None = None  # days between the delivery and the stockout


@dataclass
class Rejection:
    name: str
    reasons: list[str]


@dataclass
class Choice:
    option: Option
    reason: str
    source: str  # "gemini", "fallback" or "rules"


def evaluate_suppliers(
    stock: float,
    incoming: float,
    daily_usage: float,
    suppliers: list[Supplier],
    policy: Policy,
    buffer_days: float = 2,
) -> tuple[list[Option], list[Rejection]]:
    """Hard checks only. Every supplier ends up as an option or a rejection with reasons."""
    days = days_left(stock, incoming, daily_usage)
    options: list[Option] = []
    rejected: list[Rejection] = []

    for s in suppliers:
        if not s.approved:
            rejected.append(Rejection(s.name, ["Not on the approved supplier list"]))
            continue
        if not arrives_in_time(s, days):
            rejected.append(
                Rejection(
                    s.name,
                    [f"Delivers in {s.lead_time_days:g} days, but stock runs out in {days:.1f} days"],
                )
            )
            continue

        qty = reorder_qty(
            stock, incoming, daily_usage, s.lead_time_days, buffer_days,
            unit_price=s.unit_price, budget=policy.budget,
        )
        if qty == 0:
            continue

        note = None
        if qty < s.min_order_qty:
            note = f"Rounded up to the minimum order of {s.min_order_qty}"
            qty = s.min_order_qty

        if s.stock_available is not None and s.stock_available < qty:
            rejected.append(
                Rejection(s.name, [f"Only {s.stock_available} available, {qty} needed"])
            )
            continue

        result = check_order(s, qty, policy)
        if not result.allowed:
            rejected.append(Rejection(s.name, result.reasons))
            continue

        margin = None if days is None else round(days - s.lead_time_days, 1)
        total = round(s.unit_price * qty + s.delivery_fee, 2)
        options.append(Option(s, qty, total, result, note, margin))

    return options, rejected


def build_options(
    stock: float,
    incoming: float,
    daily_usage: float,
    suppliers: list[Supplier],
    policy: Policy,
    buffer_days: float = 2,
) -> list[Option]:
    """The suppliers that passed every hard check."""
    return evaluate_suppliers(
        stock, incoming, daily_usage, suppliers, policy, buffer_days
    )[0]


def cheapest_option(options: list[Option]) -> Option:
    """Lowest total cost; faster delivery wins a tie."""
    return min(options, key=lambda o: (o.total, o.supplier.lead_time_days))


def option_facts(option: Option) -> dict:
    s = option.supplier
    return {
        "name": s.name,
        "unit_price": s.unit_price,
        "delivery_fee": s.delivery_fee,
        "min_order_qty": s.min_order_qty,
        "qty": option.qty,
        "total": option.total,
        "lead_time_days": s.lead_time_days,
        "margin_days": option.margin_days,
        "reliability": s.reliability,
        "deliveries_on_record": s.history_count,
        "needs_approval": option.policy.needs_approval,
        "note": option.note,
    }


def pick_option(options: list[Option]) -> Choice | None:
    """Gemini picks among the options. Code checks the pick is on the list."""
    if not options:
        return None
    if len(options) == 1:
        return Choice(options[0], "Only one supplier qualifies.", "rules")

    answer = choose_supplier([option_facts(o) for o in options])
    if answer:
        match = next((o for o in options if o.supplier.name == answer["name"]), None)
        if match:
            return Choice(match, answer["reason"], "gemini")

    best = cheapest_option(options)
    return Choice(
        best,
        f"{best.supplier.name} has the lowest total cost (${best.total:.2f}) "
        "among eligible suppliers.",
        "fallback",
    )


@dataclass
class Plan:
    days_left: float | None
    risk: str
    options: list[Option]
    rejected: list[Rejection]
    choice: Choice | None
    message: str


def plan_order(
    stock: float,
    incoming: float,
    daily_usage: float,
    suppliers: list[Supplier],
    policy: Policy,
    buffer_days: float = 2,
) -> Plan:
    """Build the options, let the AI choose, and explain the outcome."""
    base = recommend(stock, incoming, daily_usage, suppliers, policy, buffer_days)
    options, rejected = evaluate_suppliers(
        stock, incoming, daily_usage, suppliers, policy, buffer_days
    )
    lead = min((s.lead_time_days for s in suppliers if s.approved), default=0)
    risk = risk_level(base.days_left, lead, buffer_days)
    choice = pick_option(options)

    if choice is None:
        message = base.message
        if message == "Order recommended.":
            message = "No supplier can fill this order within the rules. Escalate to the owner."
        if message == "Stock is sufficient. No order needed.":
            rejected = []
        return Plan(base.days_left, risk, options, rejected, None, message)

    return Plan(base.days_left, risk, options, rejected, choice, "Order recommended.")
