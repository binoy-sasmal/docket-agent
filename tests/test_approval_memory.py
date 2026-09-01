"""Tests for human approval and supplier-namespaced memory writes."""

from __future__ import annotations

import pytest
from langgraph.types import Command

from docket.approval import (
    ApprovalRecord,
    ApprovalRejected,
    HumanApprovalRequired,
    record_approved_resolution,
    require_human_approval,
)
from docket.graph.langgraph_app import build_docket_graph
from docket.graph.skeleton import CaseKey, run_case
from docket.memory import SupplierMemoryStore


def test_proposal_requires_human_approval_before_side_effects() -> None:
    proposal = run_case(CaseKey("4507000477", "00060")).proposal

    with pytest.raises(HumanApprovalRequired) as exc_info:
        require_human_approval(proposal)

    assert exc_info.value.request.case_key == "4507000477/00060"
    assert exc_info.value.request.disposition == "post"


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


def test_langgraph_interrupts_before_approved_memory_write() -> None:
    app = build_docket_graph()
    config = {"configurable": {"thread_id": "approval-test"}}

    result = app.graph.invoke({"case": CaseKey("4507000477", "00060")}, config=config)

    assert app.memory_store.list_supplier("vendorID_0103") == ()
    interrupt_payload = result["__interrupt__"][0].value
    assert interrupt_payload["case_key"] == "4507000477/00060"
    assert interrupt_payload["disposition"] == "post"


def test_langgraph_resume_after_approval_writes_supplier_memory() -> None:
    app = build_docket_graph()
    config = {"configurable": {"thread_id": "approval-resume-test"}}
    app.graph.invoke({"case": CaseKey("4507000477", "00060")}, config=config)

    result = app.graph.invoke(
        Command(
            resume={
                "approved": True,
                "approved_by": "user_approver",
                "proposed_by": "agent",
                "reason": "reviewed supporting evidence",
            }
        ),
        config=config,
    )

    record = result["approval_record"]
    assert record.supplier == "vendorID_0103"
    assert record.case_purchase_order == "4507000477"
    assert app.memory_store.list_supplier("vendorID_0103") == (record,)
