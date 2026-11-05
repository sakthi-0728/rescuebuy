"""Ask Rescue AI: answers questions about the business using read-only tools.

How it stays trustworthy:
- Gemini only chooses a tool (and an item). It never answers from its own knowledge.
- Every number comes from the tools, which are plain Python over the database.
- If Gemini rewords an answer, a guard rejects it when it contains a number that is not in
  the computed facts, and the computed answer is shown instead.
- No tool can order, approve or pay. If Gemini is down, a keyword router still works.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.ai import explain_answer, route_question
from app.compare import evaluate_suppliers
from app.inventory import build_alerts
from app.lab import cheapest, simulate
from app.snapshot import Snapshot

DEFAULT_RUNOUT_DAYS = 3
DEFAULT_LATE_DAYS = 2
MAX_AI_TEXT = 600

TOOL_SPECS = [
    {"name": "stock_of", "item": "required", "days": False, "synthesize": False,
     "description": "How much of one item is in stock."},
    {"name": "days_left", "item": "required", "days": False, "synthesize": False,
     "description": "How many days one item will last at the current usage."},
    {"name": "running_out", "item": "none", "days": True, "synthesize": False,
     "description": "Which items could run out within N days (days defaults to 3)."},
    {"name": "expiring", "item": "none", "days": False, "synthesize": False,
     "description": "Which items with expiry dates are close to expiring."},
    {"name": "what_to_reorder", "item": "none", "days": False, "synthesize": True,
     "description": "What should be reordered now, from which supplier, and for how much."},
    {"name": "order_cost", "item": "none", "days": False, "synthesize": False,
     "description": "How much the recommended reorders cost in total."},
    {"name": "budget_check", "item": "none", "days": False, "synthesize": True,
     "description": "Whether the owner can afford to restock, or will exceed the monthly budget."},
    {"name": "best_supplier", "item": "optional", "days": False, "synthesize": True,
     "description": "The best eligible supplier for an item (or for every item that needs a reorder)."},
    {"name": "late_supplier", "item": "none", "days": True, "synthesize": True,
     "description": "What happens if suppliers deliver N days late (days defaults to 2)."},
    {"name": "order_status", "item": "none", "days": False, "synthesize": False,
     "description": "The status of the owner's orders."},
]
SPEC = {t["name"]: t for t in TOOL_SPECS}

STATUS_LABEL = {
    "PENDING_APPROVAL": "awaiting your approval",
    "APPROVED": "approved, ready to pay",
    "REJECTED": "rejected",
    "PAYMENT_STARTED": "waiting for PayPal",
    "AUTHORIZED": "funds reserved, waiting for delivery",
    "DELIVERED_CAPTURED": "delivered and paid",
}

EXAMPLES = [
    "How many boxes do I have?",
    "How long will the flour last?",
    "Which items could run out within three days?",
    "What should I reorder this week?",
    "How much will the recommended order cost?",
    "Can I afford to restock everything?",
    "Which supplier offers the best eligible option?",
    "What happens if a supplier delivers two days late?",
]


@dataclass
class Intent:
    tool: str
    item: str | None = None
    days: float | None = None


@dataclass
class ToolResult:
    text: str
    facts: dict = field(default_factory=dict)
    basis: list[str] = field(default_factory=list)
    clarification: bool = False
    suggestions: list[str] = field(default_factory=list)


# ---- Small formatting helpers ----

def plural(n: float, word: str) -> str:
    return f"{n:g} {word}" if n == 1 else f"{n:g} {word}s"


def days_text(days: float | None) -> str:
    return "no usage on record" if days is None else plural(round(days, 1), "day")


def money(value: float) -> str:
    return f"${value:,.2f}"


def names_list(names: list[str]) -> str:
    return ", ".join(names)


# ---- Reading the question without AI ----

PURCHASE_RE = re.compile(
    r"^\s*(please\s+|can you\s+|could you\s+)?"
    r"(buy|order|purchase|pay|approve|place|send|reorder|restock)\b(?!\s+(status|history))",
    re.IGNORECASE,
)
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fourteen": 14,
}
DAYS_RE = re.compile(r"(\d+(?:\.\d+)?|" + "|".join(NUMBER_WORDS) + r")\s*(?:more\s+)?days?\b", re.IGNORECASE)


def find_days(question: str) -> float | None:
    m = DAYS_RE.search(question)
    if not m:
        return None
    raw = m.group(1).lower()
    return float(NUMBER_WORDS[raw]) if raw in NUMBER_WORDS else float(raw)


def _forms(word: str) -> set[str]:
    forms = {word}
    if word.endswith("es") and len(word) > 4:
        forms.add(word[:-2])
    if word.endswith("s") and len(word) > 3:
        forms.add(word[:-1])
    return forms


def find_items(question: str, names: list[str]) -> list[str]:
    """Items the question mentions. More than one means it is ambiguous."""
    words = set()
    for w in re.findall(r"[a-z]+", question.lower()):
        words |= _forms(w)
    scored = []
    for name in names:
        tokens = [t for t in re.findall(r"[a-z]+", name.lower()) if len(t) >= 3]
        score = sum(1 for t in tokens if _forms(t) & words)
        if score:
            scored.append((score, name))
    if not scored:
        return []
    best = max(score for score, _ in scored)
    return [name for score, name in scored if score == best]


def keyword_route(question: str, snap: Snapshot) -> Intent:
    q = question.lower()
    names = [i.name for i in snap.items]
    matched = find_items(question, names)
    item = matched[0] if len(matched) == 1 else None
    days = find_days(question)

    def has(pattern: str) -> bool:
        return re.search(pattern, q) is not None

    if has(r"\b(late|delay|delayed|behind schedule)\b"):
        return Intent("late_supplier", days=days)
    if has(r"\b(afford|budget|overspend|exceed)\b"):
        return Intent("budget_check")
    if has(r"\b(cost|costs|price|spend)\b"):
        return Intent("order_cost")
    if has(r"\b(expire|expires|expiry|expiring|spoil|spoiling|shelf life)\b"):
        return Intent("expiring")
    if has(r"\b(supplier|suppliers|wholesaler|wholesalers|vendor|vendors|cheapest)\b"):
        return Intent("best_supplier", item=item)
    if has(r"\b(reorder|restock|replenish|re-order)\b") or has(r"\b(what|which)\b.*\b(buy|order)\b") or has(
        r"\bneed to (buy|order)\b"
    ):
        return Intent("what_to_reorder")
    if has(r"\b(status|pending|waiting|delivered|track|my orders)\b"):
        return Intent("order_status")
    if matched:
        if has(r"\b(run out|runs out|running out|last|lasts|how long|how many days|days left|enough)\b"):
            return Intent("days_left", item=item)
        return Intent("stock_of", item=item)
    if has(r"\b(run out|runs out|running out|low|shortage|stockout|out of stock)\b"):
        return Intent("running_out", days=days)
    if has(r"\b(how many|how much|stock|have|left)\b"):
        return Intent("stock_of")
    return Intent("none")


def validate_route(raw: dict | None, snap: Snapshot) -> Intent | None:
    """Accept the AI's choice only if it names a real tool and a real item."""
    if not raw or raw.get("tool") not in SPEC:
        return None
    spec = SPEC[raw["tool"]]
    names = {i.name.lower(): i.name for i in snap.items}
    item = names.get((raw.get("item") or "").lower())
    days = raw.get("days")
    if days is not None and not (0 < days <= 60):
        days = None
    return Intent(spec["name"], item=item if spec["item"] != "none" else None, days=days)


# ---- The tools ----

def ask_which_item(snap: Snapshot, tool: str) -> ToolResult:
    names = [i.name for i in snap.items]
    templates = {
        "stock_of": "What is my stock of {}?",
        "days_left": "How long will my {} last?",
    }
    template = templates.get(tool, "What is my stock of {}?")
    return ToolResult(
        text=f"Which item do you mean? I keep track of: {names_list(names)}.",
        clarification=True,
        suggestions=[template.format(n) for n in names],
    )


def tool_stock_of(snap: Snapshot, intent: Intent) -> ToolResult:
    v = snap.view(intent.item)
    text = f"{v['item']}: you have {v['stock']:g} {v['unit']} in stock."
    if v["days_left"] is None:
        text += " There is no usage on record, so I cannot estimate how long it lasts."
    else:
        text += f" At about {v['daily_usage']:g} {v['unit']} a day that lasts {days_text(v['days_left'])}."
    basis = [
        f"Stock: {v['stock']:g} {v['unit']} (inventory record)",
        f"Usage: {v['daily_usage']:g} {v['unit']} a day (average on record, not a live feed)",
    ]
    if v["last_restocked"]:
        basis.append(f"Last restocked: {v['last_restocked']}")
    facts = {k: v[k] for k in ("item", "unit", "stock", "daily_usage", "days_left", "last_restocked")}
    return ToolResult(text, facts, basis)


def tool_days_left(snap: Snapshot, intent: Intent) -> ToolResult:
    v = snap.view(intent.item)
    if v["days_left"] is None:
        return ToolResult(
            f"{v['item']} has no usage on record, so I cannot estimate how long it lasts.",
            {"item": v["item"], "stock": v["stock"]},
            [f"Stock: {v['stock']:g} {v['unit']} (inventory record)", "Usage: none on record"],
        )
    text = (
        f"{v['item']} should last about {days_text(v['days_left'])}: "
        f"{v['stock']:g} {v['unit']} at {v['daily_usage']:g} {v['unit']} a day."
    )
    lead = v["fastest_lead_time_days"]
    if lead is not None:
        text += f" The fastest supplier delivers in {plural(lead, 'day')}."
    dte = v["days_to_expiry"]
    if dte is not None and dte >= 0:
        if v["expiring_unused"] > 0:
            text += f" It expires in {plural(dte, 'day')}, so about {v['expiring_unused']:g} {v['unit']} may go unused."
        else:
            text += f" It expires in {plural(dte, 'day')} but should be used in time."
    basis = [
        f"Days left = stock ({v['stock']:g}) divided by daily usage ({v['daily_usage']:g})",
        "Usage is the average on record, so a busy week would shorten this",
    ]
    facts = {k: v[k] for k in ("item", "unit", "stock", "daily_usage", "days_left",
                               "fastest_lead_time_days", "days_to_expiry", "expiring_unused")}
    return ToolResult(text, facts, basis)


def tool_running_out(snap: Snapshot, intent: Intent) -> ToolResult:
    window = intent.days if intent.days is not None else DEFAULT_RUNOUT_DAYS
    hits = sorted(
        (v for v in snap.views if v["days_left"] is not None and v["days_left"] <= window),
        key=lambda v: v["days_left"],
    )
    basis = ["Days left = stock divided by average daily usage", "Items with no usage on record are not included"]
    if not hits:
        return ToolResult(
            f"No item is expected to run out within {plural(window, 'day')}.",
            {"days": window, "items": []}, basis,
        )
    listing = names_list([f"{v['item']} ({days_text(v['days_left'])})" for v in hits])
    return ToolResult(
        f"Within {plural(window, 'day')}: {listing}.",
        {"days": window, "items": [{"item": v["item"], "days_left": v["days_left"]} for v in hits]},
        basis,
    )


def tool_expiring(snap: Snapshot, intent: Intent) -> ToolResult:
    alerts = [a for a in build_alerts(snap.views) if a["kind"] == "expiry"]
    basis = ["Only items with an expiry date on record are checked"]
    if not alerts:
        return ToolResult("No item with an expiry date is close to expiring.", {"items": []}, basis)
    return ToolResult(
        " ".join(f"{a['item']}: {a['reason']}" for a in alerts),
        {"items": [{"item": a["item"], "reason": a["reason"]} for a in alerts]},
        basis,
    )


def reorder_lines(snap: Snapshot):
    candidates, unfillable = snap.candidates()
    lines = []
    for c in candidates:
        o = cheapest(c)
        lines.append(
            {"item": c.item, "unit": c.unit, "qty": o.qty, "supplier": o.supplier.name,
             "total": o.total, "days_left": c.days_left, "risk": c.risk}
        )
    return lines, unfillable


def tool_what_to_reorder(snap: Snapshot, intent: Intent) -> ToolResult:
    lines, unfillable = reorder_lines(snap)
    basis = [
        "Quantity covers usage during delivery plus a safety buffer, minus stock on hand",
        "Supplier shown is the lowest total cost among eligible suppliers",
    ]
    if not lines and not unfillable:
        return ToolResult("Nothing needs reordering right now.", {"items": []}, basis)
    parts = []
    total = round(sum(line["total"] for line in lines), 2)
    if lines:
        listing = names_list([f"{l['item']}: {l['qty']:g} {l['unit']} from {l['supplier']} ({money(l['total'])})" for l in lines])
        parts.append(f"Reorder now: {listing}. Together that is {money(total)}.")
    if unfillable:
        parts.append(f"No eligible supplier for {names_list(unfillable)}, so escalate those to yourself.")
    parts.append("I cannot place orders. You review and approve each one yourself.")
    return ToolResult(" ".join(parts), {"items": lines, "total": total, "unfillable": unfillable}, basis)


def cost_numbers(snap: Snapshot) -> dict:
    lines, _ = reorder_lines(snap)
    cost = round(sum(line["total"] for line in lines), 2)
    b = snap.budget()
    return {
        "cost": cost, "remaining": b["remaining"], "spent": b["spent"], "monthly": b["monthly"],
        "short_by": round(cost - b["remaining"], 2), "items": len(lines),
    }


def tool_order_cost(snap: Snapshot, intent: Intent) -> ToolResult:
    n = cost_numbers(snap)
    basis = ["Cheapest eligible supplier for each item that needs a reorder, delivery included"]
    if n["items"] == 0:
        return ToolResult("Nothing needs reordering, so there is nothing to pay for right now.", n, basis)
    text = f"Reordering everything that needs it costs {money(n['cost'])} across {plural(n['items'], 'item')}."
    text += f" You have {money(n['remaining'])} left this month."
    return ToolResult(text, n, basis + [f"Budget: {money(n['spent'])} spent of {money(n['monthly'])} this month"])


def tool_budget_check(snap: Snapshot, intent: Intent) -> ToolResult:
    n = cost_numbers(snap)
    basis = [
        f"Budget: {money(n['spent'])} spent of {money(n['monthly'])} this month",
        "Restock cost: cheapest eligible supplier for each item that needs a reorder",
    ]
    text = f"You have spent {money(n['spent'])} of your {money(n['monthly'])} budget this month, leaving {money(n['remaining'])}."
    if n["items"] == 0:
        text += " Nothing needs restocking right now."
    elif n["short_by"] > 0:
        text += (
            f" Restocking everything costs {money(n['cost'])}, so you cannot afford all of it:"
            f" you would be {money(n['short_by'])} over. The Decision Lab shows what fits."
        )
    else:
        text += f" Restocking everything costs {money(n['cost'])}, which fits, leaving {money(n['remaining'] - n['cost'])}."
    return ToolResult(text, n, basis)


def tool_best_supplier(snap: Snapshot, intent: Intent) -> ToolResult:
    basis = [
        "Eligible means approved, arriving before stock runs out, able to fill the order, within budget limits",
        "Best means the lowest total cost, delivery included",
    ]
    if intent.item is None:
        lines, unfillable = reorder_lines(snap)
        if not lines:
            return ToolResult("Nothing needs reordering, so there is no supplier to pick right now.", {"items": []}, basis)
        listing = names_list([f"{l['item']}: {l['supplier']} ({money(l['total'])})" for l in lines])
        text = f"Best eligible supplier for each item that needs a reorder: {listing}."
        if unfillable:
            text += f" No eligible supplier for {names_list(unfillable)}."
        return ToolResult(text, {"items": lines, "unfillable": unfillable}, basis)

    item = snap.item(intent.item)
    suppliers = snap.offers.get(item.name, [])
    options, rejected = evaluate_suppliers(
        item.stock, item.incoming, item.daily_usage, suppliers, snap.policy, snap.buffer_days
    )
    if not options:
        v = snap.view(item.name)
        if v["risk"] == "ok":
            return ToolResult(
                f"{item.name} does not need a reorder: it has {days_text(v['days_left'])} of stock.",
                {"item": item.name, "days_left": v["days_left"]}, basis,
            )
        return ToolResult(
            f"No supplier is eligible for {item.name} right now. Escalate this one to yourself.",
            {"item": item.name, "rejected": [{"name": r.name, "reasons": r.reasons} for r in rejected]}, basis,
        )
    ranked = sorted(options, key=lambda o: (o.total, o.supplier.lead_time_days))
    best = ranked[0]
    text = (
        f"For {item.name}, {best.supplier.name} has the lowest total: {best.qty:g} {item.unit} for "
        f"{money(best.total)}, arriving in {plural(best.supplier.lead_time_days, 'day')}."
    )
    if len(ranked) > 1:
        text += " Other eligible: " + names_list(
            [f"{o.supplier.name} ({money(o.total)}, {plural(o.supplier.lead_time_days, 'day')})" for o in ranked[1:]]
        ) + "."
    if rejected:
        text += " Not eligible: " + "; ".join(f"{r.name} ({r.reasons[0]})" for r in rejected) + "."
    facts = {
        "item": item.name,
        "best": {"supplier": best.supplier.name, "qty": best.qty, "total": best.total,
                 "lead_time_days": best.supplier.lead_time_days},
        "others": [{"supplier": o.supplier.name, "total": o.total, "lead_time_days": o.supplier.lead_time_days}
                   for o in ranked[1:]],
        "rejected": [{"name": r.name, "reasons": r.reasons} for r in rejected],
    }
    return ToolResult(text, facts, basis)


def tool_late_supplier(snap: Snapshot, intent: Intent) -> ToolResult:
    delay = intent.days if intent.days is not None else DEFAULT_LATE_DAYS
    candidates, _ = snap.candidates()
    basis = [
        "Arrival = supplier lead time plus the delay; compared with days of stock left",
        "An estimate based on current usage, not a guarantee",
    ]
    if not candidates:
        return ToolResult(
            "Nothing needs replenishing right now, so a late delivery would not affect anything yet.",
            {"delay_days": delay}, basis,
        )
    budget = max(0.0, snap.budget()["remaining"])
    results = {r.key: r for r in simulate(candidates, budget, delay_days=delay)}

    def describe(key: str, label: str) -> str:
        exposed = results[key].exposed
        if not exposed:
            return f"{label}: no item would run out."
        listing = names_list([f"{e['item']} ({plural(e['stockout_days'], 'day')} without stock)" for e in exposed])
        return f"{label}: {listing}."

    text = (
        f"If suppliers deliver {plural(delay, 'day')} late: "
        + describe("all_fastest", "Buying from the fastest suppliers")
        + " "
        + describe("all_cheapest", "Buying from the cheapest")
    )
    facts = {
        "delay_days": delay,
        "fastest_exposed": results["all_fastest"].exposed,
        "cheapest_exposed": results["all_cheapest"].exposed,
    }
    return ToolResult(text, facts, basis)


def tool_order_status(snap: Snapshot, intent: Intent) -> ToolResult:
    if not snap.orders:
        return ToolResult("You have no orders yet.", {"orders": []}, ["Orders are listed on the Overview tab"])
    lines = [
        f"Order {o.id}: {o.item} from {o.supplier_name}, {money(o.total)}, {STATUS_LABEL.get(o.status.value, o.status.value)}."
        for o in snap.orders
    ]
    facts = {"orders": [{"id": o.id, "item": o.item, "total": o.total, "status": o.status.value} for o in snap.orders]}
    return ToolResult(" ".join(lines), facts, ["Payment is only taken when delivery is confirmed"])


TOOLS = {
    "stock_of": tool_stock_of,
    "days_left": tool_days_left,
    "running_out": tool_running_out,
    "expiring": tool_expiring,
    "what_to_reorder": tool_what_to_reorder,
    "order_cost": tool_order_cost,
    "budget_check": tool_budget_check,
    "best_supplier": tool_best_supplier,
    "late_supplier": tool_late_supplier,
    "order_status": tool_order_status,
}


def refusal() -> ToolResult:
    return ToolResult(
        "I cannot place, approve or pay for orders. You approve every order yourself: use Review reorder or the "
        "Decision Lab to create one, then approve and pay on the Orders list.",
        {}, ["Orders need your approval, and payment is only taken when delivery is confirmed"],
        suggestions=["What should I reorder this week?"],
    )


def help_result() -> ToolResult:
    return ToolResult(
        "I can answer questions about your stock, how long it lasts, what to reorder, supplier options, your budget, "
        "late deliveries and your orders. I cannot place orders.",
        {}, [], clarification=True, suggestions=EXAMPLES[:4],
    )


# ---- Checking the AI's wording ----

NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
SPELLED = {w: n for w, n in NUMBER_WORDS.items() if w != "one"}
ACTION_CLAIM_RE = re.compile(
    r"\b(i('ve| have)?|we('ve| have)?)\s+(ordered|placed|purchased|paid|approved|bought)\b", re.IGNORECASE
)


def numbers_in(text: str) -> list[float]:
    found = [float(m.replace(",", "")) for m in NUM_RE.findall(text)]
    found += [float(SPELLED[w]) for w in re.findall(r"[a-z]+", text.lower()) if w in SPELLED]
    return found


def collect_numbers(value, out: set[float]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        out.update({float(value), round(value, 1), round(value, 2), float(round(value))})
    elif isinstance(value, str):
        out.update(numbers_in(value))
    elif isinstance(value, dict):
        for v in value.values():
            collect_numbers(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            collect_numbers(v, out)


def ai_text_is_safe(text: str, question: str, result: ToolResult) -> bool:
    """True only if the text adds no numbers, claims no action and is not rambling."""
    if not text or len(text) > MAX_AI_TEXT or ACTION_CLAIM_RE.search(text):
        return False
    allowed: set[float] = set()
    collect_numbers(result.facts, allowed)
    allowed.update(numbers_in(result.text))
    allowed.update(numbers_in(" ".join(result.basis)))
    allowed.update(numbers_in(question))
    return all(any(abs(n - a) <= 0.011 for a in allowed) for n in numbers_in(text))


# ---- Putting it together ----

def run_tool(intent: Intent, snap: Snapshot) -> ToolResult:
    if intent.tool == "none":
        return help_result()
    spec = SPEC[intent.tool]
    if spec["item"] == "required" and (intent.item is None or snap.view(intent.item) is None):
        return ask_which_item(snap, intent.tool)
    return TOOLS[intent.tool](snap, intent)


def answer_question(question: str, snap: Snapshot) -> dict:
    question = question.strip()
    if PURCHASE_RE.match(question):
        intent, routed_by, result = Intent("refuse_action"), "rules", refusal()
    else:
        raw = route_question(question, TOOL_SPECS, [i.name for i in snap.items])
        intent = validate_route(raw, snap)
        routed_by = "gemini"
        if intent is None or intent.tool == "none":
            intent, routed_by = keyword_route(question, snap), "keywords"
        result = run_tool(intent, snap)

    text, source = result.text, "calculated"
    spec = SPEC.get(intent.tool)
    if spec and spec["synthesize"] and not result.clarification:
        candidate = explain_answer(question, result.text, result.facts)
        if candidate and ai_text_is_safe(candidate, question, result):
            text, source = candidate, "gemini"

    return {
        "question": question,
        "tool": intent.tool,
        "routed_by": routed_by,
        "answer": {"text": text, "source": source},
        "basis": result.basis,
        "data": result.facts,
        "needs_clarification": result.clarification,
        "suggestions": result.suggestions,
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
