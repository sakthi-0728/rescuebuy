"""Decision Lab: compare purchasing strategies before spending anything.

Everything here is deterministic and read-only. It never creates an order, never talks
to PayPal and never changes stock. The AI only explains the results afterwards.
"""
from dataclasses import dataclass, field

from app.compare import Option, evaluate_suppliers
from app.forecast import days_left as calc_days_left
from app.forecast import risk_level
from app.inventory import Item
from app.policy import Policy
from app.suppliers import Supplier

RISK_RANK = {"critical": 0, "warning": 1, "ok": 2}
BASELINE_KEY = "all_fastest"

SCENARIO_DEFS = [
    ("all_cheapest", "Buy everything now, cheapest supplier",
     "Replenish every item that needs it from the supplier with the lowest total cost."),
    ("all_fastest", "Buy everything now, fastest supplier",
     "Replenish every item that needs it from the quickest supplier. Safest, usually costliest."),
    ("critical_only", "Critical items only, the rest waits",
     "Buy only what is critical today and re-check the rest after your waiting time."),
    ("fit_budget", "Fit the budget by urgency",
     "Spend the budget on the most urgent items first and let the rest wait."),
]


@dataclass
class Candidate:
    item: str
    unit: str
    days_left: float | None
    daily_usage: float
    criticality: int
    risk: str
    options: list[Option]


@dataclass
class Line:
    item: str
    supplier: str
    qty: int
    total: float
    lead_time_days: float
    arrives_in_days: float
    margin_days: float | None  # days of stock still left when it arrives (negative = gap)
    stockout_days: float       # days without stock before it arrives


@dataclass
class Deferred:
    item: str
    can_wait: bool
    margin_days: float | None
    stockout_days: float
    order_within_days: float | None  # latest day to order from the fastest supplier


@dataclass
class ScenarioResult:
    key: str
    name: str
    description: str
    spend: float
    budget_remaining: float
    over_budget: bool
    bought: list[Line]
    deferred: list[Deferred]
    exposed: list[dict]
    savings_vs_baseline: float = 0.0


def priority_key(c: Candidate):
    days = c.days_left if c.days_left is not None else float("inf")
    return (RISK_RANK[c.risk], -c.criticality, days, c.item)


def build_candidates(
    items: list[Item],
    offers: dict[str, list[Supplier]],
    policy: Policy,
    buffer_days: float,
) -> tuple[list[Candidate], list[str]]:
    """Items that need a reorder and can get one, plus at-risk items nobody can supply."""
    candidates: list[Candidate] = []
    unfillable: list[str] = []
    for it in items:
        suppliers = offers.get(it.name, [])
        days = calc_days_left(it.stock, it.incoming, it.daily_usage)
        lead = min((s.lead_time_days for s in suppliers if s.approved), default=0)
        risk = risk_level(days, lead, buffer_days)
        options, _ = evaluate_suppliers(
            it.stock, it.incoming, it.daily_usage, suppliers, policy, buffer_days
        )
        if options:
            candidates.append(
                Candidate(it.name, it.unit, days, it.daily_usage, it.criticality, risk, options)
            )
        elif risk != "ok":
            unfillable.append(it.name)
    candidates.sort(key=priority_key)
    return candidates, unfillable


def cheapest(c: Candidate) -> Option:
    return min(c.options, key=lambda o: (o.total, o.supplier.lead_time_days))


def fastest(c: Candidate) -> Option:
    return min(c.options, key=lambda o: (o.supplier.lead_time_days, o.total))


def make_line(c: Candidate, option: Option, delay_days: float) -> Line:
    arrives = option.supplier.lead_time_days + delay_days
    margin = None if c.days_left is None else round(c.days_left - arrives, 1)
    gap = 0.0 if margin is None else max(0.0, -margin)
    return Line(
        c.item, option.supplier.name, option.qty, option.total,
        option.supplier.lead_time_days, arrives, margin, round(gap, 1),
    )


def make_deferred(c: Candidate, wait_days: float, delay_days: float) -> Deferred:
    """What happens if this item waits, then is ordered from the fastest supplier."""
    f = fastest(c)
    lead = f.supplier.lead_time_days
    if c.days_left is None:
        return Deferred(c.item, True, None, 0.0, None)
    margin = round(c.days_left - (wait_days + lead + delay_days), 1)
    gap = max(0.0, -margin)
    return Deferred(
        c.item, gap == 0, margin, round(gap, 1), round(c.days_left - lead - delay_days, 1)
    )


def select(key: str, candidates: list[Candidate], budget: float):
    """Which items are bought now (with which option) and which wait."""
    if key == "all_cheapest":
        return [(c, cheapest(c)) for c in candidates], []
    if key == "all_fastest":
        return [(c, fastest(c)) for c in candidates], []
    if key == "critical_only":
        bought = [(c, cheapest(c)) for c in candidates if c.risk == "critical"]
        waiting = [c for c in candidates if c.risk != "critical"]
        return bought, waiting
    if key == "fit_budget":
        remaining = budget
        bought, waiting = [], []
        for c in candidates:  # already in priority order
            option = cheapest(c)
            if round(option.total - remaining, 2) <= 0:
                bought.append((c, option))
                remaining -= option.total
            else:
                waiting.append(c)
        return bought, waiting
    raise ValueError(f"Unknown scenario: {key}")


def simulate(
    candidates: list[Candidate],
    budget: float,
    delay_days: float = 0.0,
    wait_days: float = 2.0,
) -> list[ScenarioResult]:
    results = []
    for key, name, description in SCENARIO_DEFS:
        bought, waiting = select(key, candidates, budget)
        lines = [make_line(c, o, delay_days) for c, o in bought]
        deferred = [make_deferred(c, wait_days, delay_days) for c in waiting]
        spend = round(sum(line.total for line in lines), 2)
        exposed = [
            {"item": line.item, "stockout_days": line.stockout_days}
            for line in lines
            if line.stockout_days > 0
        ] + [
            {"item": d.item, "stockout_days": d.stockout_days}
            for d in deferred
            if d.stockout_days > 0
        ]
        results.append(
            ScenarioResult(
                key, name, description, spend, round(budget - spend, 2),
                round(spend - budget, 2) > 0, lines, deferred, exposed,
            )
        )
    baseline = next(r.spend for r in results if r.key == BASELINE_KEY)
    for r in results:
        r.savings_vs_baseline = round(baseline - r.spend, 2)
    return results


def recommended_key(results: list[ScenarioResult]) -> str:
    """Within budget first, then the fewest items exposed to a stockout, then the lowest spend."""
    best = min(
        enumerate(results),
        key=lambda pair: (pair[1].over_budget, len(pair[1].exposed), pair[1].spend, pair[0]),
    )
    return best[1].key


def landed(option: Option) -> float:
    return option.total / option.qty


def comparison_savings(candidates: list[Candidate]) -> dict:
    """Saving from choosing the best supplier per unit instead of the costliest eligible one.

    Both are priced per unit including delivery, and compared on the same quantity.
    """
    rows = []
    for c in candidates:
        if len(c.options) < 2:
            continue
        best = min(c.options, key=lambda o: (landed(o), o.supplier.lead_time_days))
        worst = max(c.options, key=landed)
        baseline_total = round(landed(worst) * best.qty, 2)
        saving = round(baseline_total - best.total, 2)
        if saving > 0:
            rows.append(
                {
                    "item": c.item,
                    "best_supplier": best.supplier.name,
                    "baseline_supplier": worst.supplier.name,
                    "best_total": best.total,
                    "baseline_total": baseline_total,
                    "saving": saving,
                }
            )
    return {
        "basis": "Compared with the costliest eligible supplier, same quantity, delivery included.",
        "total": round(sum(r["saving"] for r in rows), 2),
        "items": rows,
    }
