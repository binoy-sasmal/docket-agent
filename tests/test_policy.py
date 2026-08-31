"""Tests for deterministic policy evaluation."""

from __future__ import annotations

from decimal import Decimal

from docket.policy import PolicyInput, TolerancePolicy, evaluate_policy


def test_exact_match_proposes_post_but_still_requires_human_approval() -> None:
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

    assert decision.reason == "exact_match"
    assert decision.within_tolerance is True
    assert decision.allowed_dispositions == ("propose_post",)
    assert decision.requires_human_approval is True


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

    assert decision.reason == "tolerable_variance"
    assert decision.within_tolerance is True
    assert decision.max_abs_variance == Decimal("0.50")


def test_required_missing_goods_receipt_needs_review() -> None:
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
    assert decision.allowed_dispositions == ("needs_review",)


def test_large_invoice_variance_escalates() -> None:
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

    assert decision.reason == "invoice_variance_exceeds_tolerance"
    assert decision.within_tolerance is False
    assert decision.allowed_dispositions == ("escalate",)
