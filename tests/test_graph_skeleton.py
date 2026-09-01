"""Tests for the minimal four-node investigation skeleton."""

from __future__ import annotations

import inspect

from docket.graph.skeleton import CaseKey, policy_gate, reconciler, run_case


def test_happy_path_runs_one_case_end_to_end_without_posting() -> None:
    result = run_case(CaseKey("4507000477", "00060"))

    assert result.policy.within_tolerance is True
    assert result.policy.reason == "matched_3way"
    assert result.proposal.disposition == "post"
    assert result.proposal.can_post is False
    assert result.proposal.supplier == "vendorID_0103"
    assert [call.name for call in result.investigation.tool_calls] == [
        "get_A_PurchaseOrder",
        "get_A_PurchaseOrderItem",
        "list_A_MaterialDocumentItem",
        "list_A_SupplierInvoiceItemPurOrdRef",
    ]


def test_two_way_match_does_not_fetch_goods_receipts() -> None:
    result = run_case(CaseKey("4507075965", "00050"))

    assert result.investigation.goods_receipts == ()
    assert "list_A_MaterialDocumentItem" not in [
        call.name for call in result.investigation.tool_calls
    ]
    assert result.policy.within_tolerance is True
    assert result.policy.reason == "matched_2way"


def test_reconciler_node_has_no_tool_parameter() -> None:
    assert tuple(inspect.signature(reconciler).parameters) == ("investigation",)


def test_policy_gate_is_deterministic_boundary() -> None:
    assert tuple(inspect.signature(policy_gate).parameters) == ("reconciliation",)


def test_every_proposal_claim_has_evidence() -> None:
    result = run_case(CaseKey("4507000477", "00060"))

    assert result.proposal.claims
    assert all(claim.evidence for claim in result.proposal.claims)
