"""Why an order was proposed: a plain record of what was considered, rejected and assumed.

Everything here is copied from the same calculation that produced the order. Nothing is added
by the AI. The record is stored with the order, so the owner can read it before approving and
after delivery.
"""
from app.compare import Option, Rejection, cheapest_option
from app.policy import Policy


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _option_row(option: Option, chosen: Option) -> dict:
    s = option.supplier
    return {
        "name": s.name,
        "qty": option.qty,
        "unit_price": s.unit_price,
        "delivery_fee": s.delivery_fee,
        "total": option.total,
        "lead_time_days": s.lead_time_days,
        "margin_days": option.margin_days,
        "reliability": s.reliability,
        "deliveries_on_record": s.history_count,
        "chosen": option is chosen,
    }


def decision_record(
    *,
    item,
    options: list[Option],
    rejected: list[Rejection],
    chosen: Option,
    policy: Policy,
    buffer_days: float,
    budget_remaining: float | None,
    chosen_by: str,
    reason: str | None = None,
    days_left: float | None = None,
    extra_assumptions: list[str] | None = None,
    usage_note: str | None = None,
) -> dict:
    """The audit record for one proposed order.

    chosen_by says who picked the supplier: "gemini", "fallback" (lowest total cost),
    "rules" (only one supplier qualified), "owner" (picked on the review screen) or
    "decision_lab" (the cheapest eligible supplier for the chosen strategy).
    """
    rules = ["The supplier must be on your approved list."]
    if days_left is not None:
        rules.append(
            f"The delivery must arrive before stock runs out (about {days_left:.1f} days of stock left)."
        )
    rules.append(f"The order total, delivery fee included, must stay within {_money(policy.budget)}.")
    rules.append(
        f"Orders above {_money(policy.max_auto_spend)} are flagged as large orders. "
        "Every order still needs your approval."
    )

    assumptions = [
        f"Usage stays at {item.daily_usage:g} {item.unit} a day, {usage_note or 'the average on record'}.",
        f"The quantity covers the delivery time plus a {buffer_days:g}-day buffer, "
        "rounded up to the supplier's minimum order.",
        "Supplier prices, lead times and stock levels are the demo data shown in the app.",
    ]
    assumptions.extend(extra_assumptions or [])
    if any(o.supplier.reliability is None for o in options):
        assumptions.append(
            "Reliability is shown as unknown when a supplier has fewer than 3 deliveries on record."
        )

    if reason is None:
        if chosen_by == "decision_lab":
            reason = "Chosen in the Decision Lab: the supplier with the lowest total cost for this strategy."
        elif chosen_by == "owner":
            best = cheapest_option(options)
            if best is chosen:
                reason = (
                    f"You chose {chosen.supplier.name}. It has the lowest total cost "
                    "among the suppliers that passed the rules."
                )
            else:
                extra = round(chosen.total - best.total, 2)
                reason = (
                    f"You chose {chosen.supplier.name}. It costs {_money(extra)} more than "
                    f"{best.supplier.name}, the cheapest supplier that passed the rules."
                )
        elif chosen_by == "rules":
            reason = "Only one supplier passed the rules."
        else:
            best = cheapest_option(options)
            reason = f"{best.supplier.name} has the lowest total cost among the suppliers that passed the rules."

    return {
        "chosen": {
            "supplier": chosen.supplier.name,
            "qty": chosen.qty,
            "total": chosen.total,
            "unit_price": chosen.supplier.unit_price,
            "delivery_fee": chosen.supplier.delivery_fee,
            "lead_time_days": chosen.supplier.lead_time_days,
        },
        "chosen_by": chosen_by,
        "reason": reason,
        "considered": [_option_row(o, chosen) for o in options],
        "rejected": [{"name": r.name, "reasons": list(r.reasons)} for r in rejected],
        "rules": rules,
        "assumptions": assumptions,
        "budget_remaining_before": budget_remaining,
    }


def top_action(
    *, item, options: list[Option], days_left: float | None, budget_remaining: float
) -> dict | None:
    """The single most useful next step for the briefing: the cheapest supplier that arrives in time.

    No AI is involved, so the dashboard stays fast and its numbers are always calculated.
    """
    if not options:
        return None
    best = cheapest_option(options)
    return {
        "item": item.name,
        "unit": item.unit,
        "days_left": None if days_left is None else round(days_left, 1),
        "supplier": best.supplier.name,
        "qty": best.qty,
        "total": best.total,
        "lead_time_days": best.supplier.lead_time_days,
        "fits_budget": best.total <= budget_remaining,
        "budget_remaining": round(budget_remaining, 2),
    }
