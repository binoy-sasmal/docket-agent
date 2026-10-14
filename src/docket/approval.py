"""Human-approval boundary for proposal side effects."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from docket.graph.skeleton import Proposal
from docket.memory import AuditEvent, SupplierMemory, SupplierMemoryRecord


class HumanApprovalRequired(RuntimeError):
    """Raised where a LangGraph `interrupt()` will sit in a later session."""

    def __init__(self, request: ApprovalRequest) -> None:
        self.request = request
        super().__init__(f"human approval required for {request.case_key}")


class ApprovalRejected(PermissionError):
    """Raised when an approval record does not permit a side effect."""


@dataclass(frozen=True)
class ApprovalRequest:
    case_key: str
    disposition: str
    summary: str


@dataclass(frozen=True)
class ApprovalRecord:
    approved: bool
    approved_by: str
    proposed_by: str
    reason: str


def approval_request_for(proposal: Proposal) -> ApprovalRequest:
    return ApprovalRequest(
        case_key=_case_key(proposal),
        disposition=proposal.disposition,
        summary=proposal.summary,
    )


def proposal_digest(proposal: Proposal) -> str:
    """Content hash of exactly what the human was asked to approve.

    Recorded on every audit event, so an approval can be tied to the evidence
    it was given, and part of the idempotency key, so approving a *different*
    proposal on the same thread is a new decision rather than a duplicate.
    """
    canonical = json.dumps(asdict(proposal), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def require_human_approval(proposal: Proposal) -> None:
    """Stop before side effects in non-LangGraph callers."""
    raise HumanApprovalRequired(approval_request_for(proposal))


def record_approval_requested(
    proposal: Proposal, memory_store: SupplierMemory, *, thread_id: str
) -> None:
    """Audit that a proposal is waiting on a human. Deduplicated, because the
    approval node re-runs this line every time it is resumed or replayed."""
    digest = proposal_digest(proposal)
    memory_store.append_audit(
        AuditEvent(
            event="approval_requested",
            case_key=_case_key(proposal),
            actor="agent",
            detail={"disposition": proposal.disposition, "proposal_digest": digest},
            dedupe_key=f"requested:{thread_id}:{digest}",
        )
    )


def record_approved_resolution(
    proposal: Proposal,
    approval: ApprovalRecord,
    memory_store: SupplierMemory,
    *,
    thread_id: str = "direct",
) -> SupplierMemoryRecord:
    """Record supplier memory only after a valid human approval, exactly once
    per (thread, proposal), with the decision in the audit trail either way."""
    case_key = _case_key(proposal)
    digest = proposal_digest(proposal)
    decision = {
        "disposition": proposal.disposition,
        "proposal_digest": digest,
        "proposed_by": approval.proposed_by,
        "reason": approval.reason,
    }

    why_not = None
    if not approval.approved:
        why_not = "resolution memory cannot be written without approval"
    elif approval.approved_by == approval.proposed_by:
        why_not = "resolution memory requires segregation of duties"
    if why_not is not None:
        # Every rejected attempt is a real event, so it is never deduplicated.
        memory_store.append_audit(
            AuditEvent(
                event="approval_rejected",
                case_key=case_key,
                actor=approval.approved_by,
                detail={**decision, "why": why_not},
            )
        )
        raise ApprovalRejected(why_not)

    record = SupplierMemoryRecord(
        supplier=proposal.supplier,
        kind="episodic",
        case_purchase_order=proposal.case.purchase_order,
        case_purchase_order_item=proposal.case.purchase_order_item,
        text=f"{proposal.disposition}: {proposal.summary}",
        approved_by=approval.approved_by,
    )
    key = f"{thread_id}:{digest}"
    stored, created = memory_store.write_approved(
        record,
        idempotency_key=key,
        audit=(
            AuditEvent("approval_granted", case_key, approval.approved_by, decision),
            AuditEvent(
                "memory_written",
                case_key,
                approval.approved_by,
                {"supplier": record.supplier, "kind": record.kind, "idempotency_key": key},
            ),
        ),
    )
    if not created:
        memory_store.append_audit(
            AuditEvent(
                "duplicate_approval_ignored",
                case_key,
                approval.approved_by,
                {"idempotency_key": key},
            )
        )
    return stored


def _case_key(proposal: Proposal) -> str:
    return f"{proposal.case.purchase_order}/{proposal.case.purchase_order_item}"
