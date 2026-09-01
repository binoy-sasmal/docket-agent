"""Deterministic policy checks for invoice exception proposals.

`Disposition` matches evals/golden/day3_labels.json's disposition_schema
exactly (frozen, AGENTS.md/docs/PROJECT.md 6.1) -- five values, no more, no
fewer. Any golden label the harness cannot reproduce with these five values
is an implementation gap, not a labelling error.

`PolicyReason` is a strict superset of that schema's six reason codes: it
adds three fallback codes (missing_goods_receipt, under_invoiced,
goods_receipt_variance_exceeds_tolerance) for patterns that exist in the
fixture universe but not among the 30 frozen labels, so evaluate_policy has
a defensible answer outside the golden set too. Only the six frozen codes
are load-bearing for the golden set; the eval harness never asserts on the
other three.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

Disposition = Literal["post", "hold", "request_credit_memo", "escalate", "route"]
PolicyReason = Literal[
    "matched_3way",
    "matched_2way",
    "no_invoice",
    "missing_goods_receipt",
    "over_invoiced",
    "under_invoiced",
    "over_receipted_no_invoice",
    "goods_receipt_variance_exceeds_tolerance",
    "consignment",
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
    is_consignment: bool = False
    """PurchaseOrderItemCategory == "Consignment". Checked before anything
    else: consignment items are invoiced through a separate process and are
    always routed away from standard 3-way/2-way matching (docs/PROJECT.md
    1, 10), regardless of what evidence happens to be present.
    """


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
    gr_variance = policy_input.goods_receipt_variance
    gr_abs_variance = abs(gr_variance) if gr_variance is not None else Decimal("0")
    invoice_abs_variance = abs(policy_input.invoice_variance)
    max_abs_variance = max(gr_abs_variance, invoice_abs_variance)

    if policy_input.is_consignment:
        return _decision(
            "consignment",
            tolerance,
            max_abs_variance,
            within_tolerance=True,
            dispositions=("route",),
        )

    if policy_input.invoice_count == 0:
        # A GR total that overshoots the PO amount with no invoice yet is an
        # anomaly a human should look at (over-delivery or a receipt error);
        # a GR total that merely falls short (or none at all) is the normal
        # "still waiting" case -- both get "hold", not "escalate".
        over_received = (
            policy_input.goods_receipt_expected
            and gr_variance is not None
            and gr_variance > tolerance
        )
        if over_received:
            return _decision(
                "over_receipted_no_invoice",
                tolerance,
                max_abs_variance,
                within_tolerance=False,
                dispositions=("escalate",),
            )
        return _decision(
            "no_invoice",
            tolerance,
            max_abs_variance,
            within_tolerance=False,
            dispositions=("hold",),
        )

    if policy_input.goods_receipt_expected and policy_input.goods_receipt_count == 0:
        return _decision(
            "missing_goods_receipt",
            tolerance,
            max_abs_variance,
            within_tolerance=False,
            dispositions=("hold",),
        )

    if invoice_abs_variance > tolerance:
        if policy_input.invoice_variance > 0:
            return _decision(
                "over_invoiced",
                tolerance,
                max_abs_variance,
                within_tolerance=False,
                dispositions=("request_credit_memo",),
            )
        return _decision(
            "under_invoiced",
            tolerance,
            max_abs_variance,
            within_tolerance=False,
            dispositions=("escalate",),
        )

    if gr_abs_variance > tolerance:
        return _decision(
            "goods_receipt_variance_exceeds_tolerance",
            tolerance,
            max_abs_variance,
            within_tolerance=False,
            dispositions=("escalate",),
        )

    reason: PolicyReason = (
        "matched_3way" if policy_input.goods_receipt_expected else "matched_2way"
    )
    return _decision(
        reason, tolerance, max_abs_variance, within_tolerance=True, dispositions=("post",)
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
