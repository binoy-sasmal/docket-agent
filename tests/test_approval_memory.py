"""Tests for human approval and supplier-namespaced memory writes."""

from __future__ import annotations

import pytest

from docket.approval import (
    ApprovalRecord,
    ApprovalRejected,
    HumanApprovalRequired,
    record_approved_resolution,
    require_human_approval,
)
from docket.graph.skeleton import CaseKey, run_case
from docket.memory import SupplierMemoryStore


def test_proposal_requires_human_approval_before_side_effects() -> None:
    proposal = run_case(CaseKey("4507000477", "00060")).proposal

    with pytest.raises(HumanApprovalRequired) as exc_info:
        require_human_approval(proposal)

    assert exc_info.value.request.case_key == "4507000477/00060"
    assert exc_info.value.request.disposition == "propose_post"


def test_unapproved_resolution_does_not_write_memory() -> None:
    proposal = run_case(CaseKey("4507000477", "00060")).proposal
    memory = SupplierMemoryStore()

    with pytest.raises(ApprovalRejected, match="without approval"):
        record_approved_resolution(
            proposal,
            ApprovalRecord(
                approved=False,
                approved_by="user_approver",
                proposed_by="agent",
                reason="not approved",
            ),
            memory,
        )

    assert memory.list_supplier(proposal.supplier) == ()


def test_approved_resolution_writes_supplier_namespaced_memory() -> None:
    proposal = run_case(CaseKey("4507000477", "00060")).proposal
    memory = SupplierMemoryStore()

    record = record_approved_resolution(
        proposal,
        ApprovalRecord(
            approved=True,
            approved_by="user_approver",
            proposed_by="agent",
            reason="reviewed supporting evidence",
        ),
        memory,
    )

    assert record.supplier == "vendorID_0103"
    assert record.kind == "episodic"
    assert memory.list_supplier("vendorID_0103") == (record,)
    assert memory.list_supplier("vendorID_9999") == ()


def test_same_actor_cannot_approve_resolution_memory_write() -> None:
    proposal = run_case(CaseKey("4507000477", "00060")).proposal
    memory = SupplierMemoryStore()

    with pytest.raises(ApprovalRejected, match="segregation"):
        record_approved_resolution(
            proposal,
            ApprovalRecord(
                approved=True,
                approved_by="same_user",
                proposed_by="same_user",
                reason="self approval",
            ),
            memory,
        )

    assert memory.list_supplier(proposal.supplier) == ()
