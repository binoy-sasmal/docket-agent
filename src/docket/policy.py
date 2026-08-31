"""Deterministic policy checks for invoice exception proposals."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

Disposition = Literal["propose_post", "needs_review", "escalate"]
PolicyReason = Literal[
    "exact_match",
    "tolerable_variance",
    "missing_goods_receipt",
    "missing_invoice",
    "goods_receipt_variance_exceeds_tolerance",
    "invoice_variance_exceeds_tolerance",
]


@dataclass(frozen=True)
class TolerancePolicy:
    """Deterministic variance thresholds.

    `relative_tolerance_bps` is basis points of the PO amount: 50 means 0.50%.
    The effective tolerance is the larger of absolute and relative tolerance.
    """

    absolute_tolerance: Decimal = Decimal("1.00")
    relative_tolerance_bps: int = 50

    def tolerance_for(self, amount: Decimal) -> Decimal:
        relative = (abs(amount) * Decimal(self.relative_tolerance_bps)) / Decimal("10000")
        return max(self.absolute_tolerance, relative)


@dataclass(frozen=True)
class PolicyInput:
    purchase_order_amount: Decimal
    goods_receipt_expected: bool
    goods_receipt_count: int
    invoice_count: int
    goods_receipt_variance: Decimal | None
    invoice_variance: Decimal


@dataclass(frozen=True)
class PolicyDecision:
    within_tolerance: bool
    reason: PolicyReason
    tolerance_amount: Decimal
    max_abs_variance: Decimal
    requires_human_approval: bool
    allowed_dispositions: tuple[Disposition, ...]


DEFAULT_TOLERANCE_POLICY = TolerancePolicy()


def evaluate_policy(
    policy_input: PolicyInput,
    policy: TolerancePolicy = DEFAULT_TOLERANCE_POLICY,
) -> PolicyDecision:
    """Apply deterministic policy. No model call belongs in this module."""
    tolerance = policy.tolerance_for(policy_input.purchase_order_amount)
    gr_abs_variance = (
        abs(policy_input.goods_receipt_variance)
        if policy_input.goods_receipt_variance is not None
        else Decimal("0")
    )
    invoice_abs_variance = abs(policy_input.invoice_variance)
    max_abs_variance = max(gr_abs_variance, invoice_abs_variance)

    if policy_input.goods_receipt_expected and policy_input.goods_receipt_count == 0:
        return _decision(
            "missing_goods_receipt",
            tolerance,
            max_abs_variance,
            within_tolerance=False,
            dispositions=("needs_review",),
        )
    if policy_input.invoice_count == 0:
        return _decision(
            "missing_invoice",
            tolerance,
            max_abs_variance,
            within_tolerance=False,
            dispositions=("needs_review",),
        )
    if gr_abs_variance > tolerance:
        return _decision(
            "goods_receipt_variance_exceeds_tolerance",
            tolerance,
            max_abs_variance,
            within_tolerance=False,
            dispositions=("escalate",),
        )
    if invoice_abs_variance > tolerance:
        return _decision(
            "invoice_variance_exceeds_tolerance",
            tolerance,
            max_abs_variance,
            within_tolerance=False,
            dispositions=("escalate",),
        )

    reason: PolicyReason = (
        "exact_match" if max_abs_variance == Decimal("0") else "tolerable_variance"
    )
    return _decision(
        reason,
        tolerance,
        max_abs_variance,
        within_tolerance=True,
        dispositions=("propose_post",),
    )


def _decision(
    reason: PolicyReason,
    tolerance_amount: Decimal,
    max_abs_variance: Decimal,
    *,
    within_tolerance: bool,
    dispositions: tuple[Disposition, ...],
) -> PolicyDecision:
    return PolicyDecision(
        within_tolerance=within_tolerance,
        reason=reason,
        tolerance_amount=tolerance_amount,
        max_abs_variance=max_abs_variance,
        requires_human_approval=True,
        allowed_dispositions=dispositions,
    )
