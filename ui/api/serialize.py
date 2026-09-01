"""Domain objects -> JSON-safe dicts for the UI.

Written out explicitly rather than via `dataclasses.asdict` plus a
`default=str` fallback. Two reasons:

1. Money must reach the browser as a *string*. `docket.schema.canonical`
   refuses to emit `Decimal` as a JSON number because JSON numbers round-trip
   through float in most readers; the same reasoning applies to a JSON API,
   and JavaScript is exactly the reader that would silently lose the
   precision. Every amount below is `str(...)`, or comes from pydantic's
   `model_dump(mode="json")`, which stringifies `Decimal` for the same reason.
2. An explicit mapping makes the wire shape a reviewed decision. In
   particular `untrusted_notes` is its own top-level array, so a client cannot
   render document free text by accident -- it has to reach for the field
   named after what it holds.
"""

from __future__ import annotations

from typing import Any

from docket.approval import ApprovalRequest
from docket.graph.skeleton import Claim, Investigation, Proposal, Reconciliation
from docket.memory import SupplierMemoryRecord
from docket.policy import PolicyDecision
from docket.tools.odata import ToolCall

# Which document class each Note field hangs off, for display. All three are
# untrusted free text (AGENTS.md: "All document free text is untrusted
# input"); the distinction is only about where a reader should go looking.
NOTE_SOURCE_FIELDS = {
    "purchase_order_item": "A_PurchaseOrderItem.Note",
    "material_document": "A_MaterialDocumentItem.Note",
    "supplier_invoice": "A_SupplierInvoiceItemPurOrdRef.Note",
}


def serialize_tool_call(index: int, call: ToolCall) -> dict[str, Any]:
    """One step of the literal trajectory.

    `sequence` is the position the tool facade recorded, not a reordering:
    `ReadOnlyODataTools.tool_calls` is append-only, so position in that tuple
    is call order. Trajectory correctness is scored on which documents were
    actually fetched, so the order shown here must be the recorded one.
    """
    return {
        "sequence": index + 1,
        "name": call.name,
        "arguments": dict(call.arguments),
    }


def serialize_claim(claim: Claim) -> dict[str, Any]:
    """A claim plus its evidence handles.

    `grounded` is computed here rather than trusted from anywhere: a claim
    carrying no evidence handle "does not count as evidence" (AGENTS.md), and
    the UI has to be able to show that state rather than quietly render an
    ungrounded sentence as though it were cited.
    """
    return {
        "text": claim.text,
        "evidence": [{"kind": handle.kind, "key": handle.key} for handle in claim.evidence],
        "grounded": bool(claim.evidence),
    }


def collect_untrusted_notes(investigation: Investigation) -> list[dict[str, Any]]:
    """Every `Note` field present on the documents this run actually read.

    Normally empty: neither `fixtures/frozen/` nor `fixtures/rendered/` carries
    note text (BPIC 2019 has none -- docs/PROJECT.md 4.2). Notes appear only
    when an eval injection overlay has been applied to the in-memory document
    copies, which is precisely when the UI most needs to show them as
    quarantined data rather than as prose.
    """
    notes: list[dict[str, Any]] = []
    item = investigation.purchase_order_item
    if item.Note:
        notes.append(
            {
                "source_kind": "purchase_order_item",
                "source_field": NOTE_SOURCE_FIELDS["purchase_order_item"],
                "source_key": f"{item.PurchaseOrder}/{item.PurchaseOrderItem}",
                "text": item.Note,
            }
        )
    for goods_receipt in investigation.goods_receipts:
        if goods_receipt.Note:
            notes.append(
                {
                    "source_kind": "material_document",
                    "source_field": NOTE_SOURCE_FIELDS["material_document"],
                    "source_key": (
                        f"{goods_receipt.MaterialDocument}/"
                        f"{goods_receipt.MaterialDocumentItem}"
                    ),
                    "text": goods_receipt.Note,
                }
            )
    for invoice in investigation.invoices:
        if invoice.Note:
            notes.append(
                {
                    "source_kind": "supplier_invoice",
                    "source_field": NOTE_SOURCE_FIELDS["supplier_invoice"],
                    "source_key": f"{invoice.SupplierInvoice}/{invoice.SupplierInvoiceItem}",
                    "text": invoice.Note,
                }
            )
    return notes


def serialize_investigation(investigation: Investigation) -> dict[str, Any]:
    return {
        "case": {
            "purchase_order": investigation.case.purchase_order,
            "purchase_order_item": investigation.case.purchase_order_item,
        },
        "purchase_order": investigation.purchase_order.model_dump(mode="json"),
        "purchase_order_item": investigation.purchase_order_item.model_dump(mode="json"),
        "goods_receipts": [
            goods_receipt.model_dump(mode="json")
            for goods_receipt in investigation.goods_receipts
        ],
        "invoices": [invoice.model_dump(mode="json") for invoice in investigation.invoices],
        "tool_calls": [
            serialize_tool_call(index, call)
            for index, call in enumerate(investigation.tool_calls)
        ],
        "purchase_order_item_key": (
            f"{investigation.purchase_order_item.PurchaseOrder}/"
            f"{investigation.purchase_order_item.PurchaseOrderItem}"
        ),
        "goods_receipt_keys": [
            f"{goods_receipt.MaterialDocument}/{goods_receipt.MaterialDocumentItem}"
            for goods_receipt in investigation.goods_receipts
        ],
        "invoice_keys": [
            f"{invoice.SupplierInvoice}/{invoice.SupplierInvoiceItem}"
            for invoice in investigation.invoices
        ],
        "untrusted_notes": collect_untrusted_notes(investigation),
    }


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def serialize_reconciliation(reconciliation: Reconciliation) -> dict[str, Any]:
    return {
        "supplier": reconciliation.supplier,
        "claims": [serialize_claim(claim) for claim in reconciliation.claims],
        "purchase_order_amount": str(reconciliation.purchase_order_amount),
        "goods_receipt_expected": reconciliation.goods_receipt_expected,
        "goods_receipt_count": reconciliation.goods_receipt_count,
        "invoice_count": reconciliation.invoice_count,
        "goods_receipt_amount": _optional_str(reconciliation.goods_receipt_amount),
        "invoice_amount": str(reconciliation.invoice_amount),
        "goods_receipt_variance": _optional_str(reconciliation.goods_receipt_variance),
        "invoice_variance": str(reconciliation.invoice_variance),
        "purchase_order_item_category": reconciliation.purchase_order_item_category,
        "narrative": reconciliation.narrative,
    }


def serialize_policy(policy: PolicyDecision) -> dict[str, Any]:
    return {
        "within_tolerance": policy.within_tolerance,
        "reason": policy.reason,
        "tolerance_amount": str(policy.tolerance_amount),
        "max_abs_variance": str(policy.max_abs_variance),
        "requires_human_approval": policy.requires_human_approval,
        "allowed_dispositions": list(policy.allowed_dispositions),
    }


def serialize_proposal(proposal: Proposal) -> dict[str, Any]:
    return {
        "disposition": proposal.disposition,
        "summary": proposal.summary,
        "supplier": proposal.supplier,
        "claims": [serialize_claim(claim) for claim in proposal.claims],
        "policy": serialize_policy(proposal.policy),
        "can_post": proposal.can_post,
    }


def serialize_approval_request(request: ApprovalRequest) -> dict[str, Any]:
    return {
        "case_key": request.case_key,
        "disposition": request.disposition,
        "summary": request.summary,
    }


def serialize_memory_record(record: SupplierMemoryRecord) -> dict[str, Any]:
    return {
        "supplier": record.supplier,
        "kind": record.kind,
        "case_purchase_order": record.case_purchase_order,
        "case_purchase_order_item": record.case_purchase_order_item,
        "text": record.text,
        "approved_by": record.approved_by,
    }
