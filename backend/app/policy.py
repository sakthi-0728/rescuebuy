from dataclasses import dataclass, field

from app.suppliers import Supplier


@dataclass
class Policy:
    max_auto_spend: float = 500   # above this, the owner must approve
    budget: float = 2000          # above this, the order is not allowed


@dataclass
class PolicyResult:
    allowed: bool
    needs_approval: bool
    reasons: list[str] = field(default_factory=list)


def check_order(supplier: Supplier, qty: int, policy: Policy) -> PolicyResult:
    """Validate an order against the business rules."""
    total = supplier.unit_price * qty

    if not supplier.approved:
        return PolicyResult(False, False, ["Supplier is not on the approved list"])

    if total > policy.budget:
        return PolicyResult(
            False, False,
            [f"Total ${total:.2f} exceeds budget ${policy.budget:.2f}"],
        )

    if total > policy.max_auto_spend:
        return PolicyResult(
            True, True,
            [f"Total ${total:.2f} exceeds the ${policy.max_auto_spend:.2f} auto-approve limit"],
        )

    return PolicyResult(True, False, [])