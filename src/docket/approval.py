"""Human-approval boundary for proposal side effects."""

from __future__ import annotations

from dataclasses import dataclass

from docket.graph.skeleton import Proposal
from docket.memory import SupplierMemoryRecord, SupplierMemoryStore


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


def require_human_approval(proposal: Proposal) -> None:
    """Stop before side effects. Later this becomes LangGraph `interrupt()`."""
    raise HumanApprovalRequired(
        ApprovalRequest(
            case_key=(
                f"{proposal.case.purchase_order}/{proposal.case.purchase_order_item}"
            ),
            disposition=proposal.disposition,
            summary=proposal.summary,
        )
    )


def record_approved_resolution(
    proposal: Proposal,
    approval: ApprovalRecord,
    memory_store: SupplierMemoryStore,
) -> SupplierMemoryRecord:
    """Record supplier memory only after a valid human approval."""
    if not approval.approved:
        raise ApprovalRejected("resolution memory cannot be written without approval")
    if approval.approved_by == approval.proposed_by:
        raise ApprovalRejected("resolution memory requires segregation of duties")

    record = SupplierMemoryRecord(
        supplier=proposal.supplier,
        kind="episodic",
        case_purchase_order=proposal.case.purchase_order,
        case_purchase_order_item=proposal.case.purchase_order_item,
        text=f"{proposal.disposition}: {proposal.summary}",
        approved_by=approval.approved_by,
    )
    memory_store.append(record)
    return record
