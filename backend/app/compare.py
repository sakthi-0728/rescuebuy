from dataclasses import dataclass

from app.ai import choose_supplier
from app.forecast import days_left, reorder_qty, risk_level
from app.policy import Policy, PolicyResult, check_order
from app.recommend import recommend
from app.suppliers import Supplier, eligible_suppliers


@dataclass
class Option:
    supplier: Supplier
    qty: int
    total: float
    policy: PolicyResult


@dataclass
class Choice:
    option: Option
    reason: str
    source: str  # "gemini", "fallback" or "rules"


def build_options(
    stock: float,
    incoming: float,
    daily_usage: float,
    suppliers: list[Supplier],
    policy: Policy,
    buffer_days: float = 2,
) -> list[Option]:
    """One option per supplier that is approved, in time, has enough stock
    to fill the order, and passes the policy."""
    days = days_left(stock, incoming, daily_usage)
    options = []
    for s in eligible_suppliers(suppliers, days):
        qty = reorder_qty(
            stock, incoming, daily_usage, s.lead_time_days, buffer_days,
            unit_price=s.unit_price, budget=policy.budget,
        )
        if qty == 0:
            continue
        if s.stock_available is not None and s.stock_available < qty:
            continue
        result = check_order(s, qty, policy)
        if not result.allowed:
            continue
        options.append(Option(s, qty, s.unit_price * qty, result))
    return options


def cheapest_option(options: list[Option]) -> Option:
    """Lowest total cost; faster delivery wins a tie."""
    return min(options, key=lambda o: (o.total, o.supplier.lead_time_days))


def option_facts(option: Option) -> dict:
    s = option.supplier
    return {
        "name": s.name,
        "unit_price": s.unit_price,
        "qty": option.qty,
        "total": option.total,
        "lead_time_days": s.lead_time_days,
        "reliability": s.reliability,
        "needs_approval": option.policy.needs_approval,
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
    options = build_options(stock, incoming, daily_usage, suppliers, policy, buffer_days)
    choice = pick_option(options)

    if choice is None:
        message = base.message
        if message == "Order recommended.":
            message = "No supplier can fill this order within the rules. Escalate to the owner."
        return Plan(base.days_left, base.risk, options, None, message)

    risk = risk_level(base.days_left, choice.option.supplier.lead_time_days, buffer_days)
    return Plan(base.days_left, risk, options, choice, "Order recommended.")