"""Tests for deterministic policy evaluation.

Disposition values asserted here match evals/golden/day3_labels.json's
disposition_schema exactly (frozen; that file is what this module exists to
satisfy). Reason codes are a superset -- see docket.policy's module
docstring: the six frozen codes plus three fallback codes for patterns
outside the golden 30, exercised by the last three tests below.
"""

from __future__ import annotations

from decimal import Decimal

from docket.policy import PolicyInput, TolerancePolicy, evaluate_policy


def test_exact_3way_match_posts_but_still_requires_human_approval() -> None:
    decision = evaluate_policy(
        PolicyInput(
            purchase_order_amount=Decimal("100.00"),
            goods_receipt_expected=True,
            goods_receipt_count=1,
            invoice_count=1,
            goods_receipt_variance=Decimal("0.00"),
            invoice_variance=Decimal("0.00"),
        )
    )

    assert decision.reason == "matched_3way"
    assert decision.within_tolerance is True
    assert decision.allowed_dispositions == ("post",)
    assert decision.requires_human_approval is True


def test_2way_match_posts_without_goods_receipt_evidence() -> None:
    decision = evaluate_policy(
        PolicyInput(
            purchase_order_amount=Decimal("100.00"),
            goods_receipt_expected=False,
            goods_receipt_count=0,
            invoice_count=1,
            goods_receipt_variance=None,
            invoice_variance=Decimal("0.00"),
        )
    )

    assert decision.reason == "matched_2way"
    assert decision.allowed_dispositions == ("post",)


def test_small_variance_is_tolerable() -> None:
    decision = evaluate_policy(
        PolicyInput(
            purchase_order_amount=Decimal("100.00"),
            goods_receipt_expected=True,
            goods_receipt_count=1,
            invoice_count=1,
            goods_receipt_variance=Decimal("0.25"),
            invoice_variance=Decimal("-0.50"),
        ),
        TolerancePolicy(absolute_tolerance=Decimal("1.00"), relative_tolerance_bps=50),
    )

    assert decision.reason == "matched_3way"
    assert decision.within_tolerance is True
    assert decision.max_abs_variance == Decimal("0.50")


def test_missing_goods_receipt_with_invoice_present_holds() -> None:
    decision = evaluate_policy(
        PolicyInput(
            purchase_order_amount=Decimal("100.00"),
            goods_receipt_expected=True,
            goods_receipt_count=0,
            invoice_count=1,
            goods_receipt_variance=Decimal("-100.00"),
            invoice_variance=Decimal("0.00"),
        )
    )

    assert decision.reason == "missing_goods_receipt"
    assert decision.within_tolerance is False
    assert decision.allowed_dispositions == ("hold",)


def test_no_invoice_holds_when_goods_receipt_is_within_tolerance() -> None:
    decision = evaluate_policy(
        PolicyInput(
            purchase_order_amount=Decimal("100.00"),
            goods_receipt_expected=True,
            goods_receipt_count=1,
            invoice_count=0,
            goods_receipt_variance=Decimal("0.00"),
            invoice_variance=Decimal("0.00"),
        )
    )

    assert decision.reason == "no_invoice"
    assert decision.allowed_dispositions == ("hold",)


def test_no_invoice_holds_when_goods_receipt_is_short_not_over() -> None:
    """Partial delivery with no invoice yet is the ordinary "still waiting"
    case, not an anomaly -- only *over*-receipt without an invoice escalates.
    """
    decision = evaluate_policy(
        PolicyInput(
            purchase_order_amount=Decimal("100.00"),
            goods_receipt_expected=True,
            goods_receipt_count=1,
            invoice_count=0,
            goods_receipt_variance=Decimal("-40.00"),
            invoice_variance=Decimal("0.00"),
        )
    )

    assert decision.reason == "no_invoice"
    assert decision.allowed_dispositions == ("hold",)


def test_over_receipted_with_no_invoice_escalates() -> None:
    decision = evaluate_policy(
        PolicyInput(
            purchase_order_amount=Decimal("100.00"),
            goods_receipt_expected=True,
            goods_receipt_count=1,
            invoice_count=0,
            goods_receipt_variance=Decimal("50.00"),
            invoice_variance=Decimal("0.00"),
        )
    )

    assert decision.reason == "over_receipted_no_invoice"
    assert decision.allowed_dispositions == ("escalate",)


def test_over_invoiced_requests_a_credit_memo() -> None:
    decision = evaluate_policy(
        PolicyInput(
            purchase_order_amount=Decimal("100.00"),
            goods_receipt_expected=False,
            goods_receipt_count=0,
            invoice_count=1,
            goods_receipt_variance=None,
            invoice_variance=Decimal("10.00"),
        )
    )

    assert decision.reason == "over_invoiced"
    assert decision.within_tolerance is False
    assert decision.allowed_dispositions == ("request_credit_memo",)


def test_under_invoiced_escalates() -> None:
    decision = evaluate_policy(
        PolicyInput(
            purchase_order_amount=Decimal("100.00"),
            goods_receipt_expected=False,
            goods_receipt_count=0,
            invoice_count=1,
            goods_receipt_variance=None,
            invoice_variance=Decimal("-10.00"),
        )
    )

    assert decision.reason == "under_invoiced"
    assert decision.allowed_dispositions == ("escalate",)


def test_goods_receipt_variance_exceeds_tolerance_escalates() -> None:
    decision = evaluate_policy(
        PolicyInput(
            purchase_order_amount=Decimal("100.00"),
            goods_receipt_expected=True,
            goods_receipt_count=1,
            invoice_count=1,
            goods_receipt_variance=Decimal("50.00"),
            invoice_variance=Decimal("0.00"),
        )
    )

    assert decision.reason == "goods_receipt_variance_exceeds_tolerance"
    assert decision.allowed_dispositions == ("escalate",)


def test_consignment_routes_regardless_of_evidence() -> None:
    decision = evaluate_policy(
        PolicyInput(
            purchase_order_amount=Decimal("0.00"),
            goods_receipt_expected=True,
            goods_receipt_count=0,
            invoice_count=0,
            goods_receipt_variance=None,
            invoice_variance=Decimal("0.00"),
            is_consignment=True,
        )
    )

    assert decision.reason == "consignment"
    assert decision.allowed_dispositions == ("route",)
