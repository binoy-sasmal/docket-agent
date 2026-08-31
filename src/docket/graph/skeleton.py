"""A minimal four-node skeleton for one invoice-exception investigation.

This is intentionally dependency-light: it preserves the node boundaries from
docs/PROJECT.md without pulling in LangGraph or a model SDK yet. Later sessions
can replace the orchestration with LangGraph while keeping these data contracts
and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from docket.policy import Disposition, PolicyDecision, PolicyInput, evaluate_policy
from docket.schema.procurement import (
    AMaterialDocumentEntry,
    APurchaseOrder,
    APurchaseOrderItem,
    ASupplierInvoiceEntry,
)
from docket.tools.odata import ReadOnlyODataTools, ToolCall

EvidenceKind = Literal["purchase_order_item", "material_document", "supplier_invoice"]


@dataclass(frozen=True)
class CaseKey:
    purchase_order: str
    purchase_order_item: str


@dataclass(frozen=True)
class EvidenceHandle:
    kind: EvidenceKind
    key: str


@dataclass(frozen=True)
class Claim:
    text: str
    evidence: tuple[EvidenceHandle, ...]


@dataclass(frozen=True)
class Investigation:
    case: CaseKey
    purchase_order: APurchaseOrder
    purchase_order_item: APurchaseOrderItem
    goods_receipts: tuple[AMaterialDocumentEntry, ...]
    invoices: tuple[ASupplierInvoiceEntry, ...]
    tool_calls: tuple[ToolCall, ...]


@dataclass(frozen=True)
class Reconciliation:
    case: CaseKey
    claims: tuple[Claim, ...]
    purchase_order_amount: Decimal
    goods_receipt_expected: bool
    goods_receipt_count: int
    invoice_count: int
    goods_receipt_amount: Decimal | None
    invoice_amount: Decimal
    goods_receipt_variance: Decimal | None
    invoice_variance: Decimal


@dataclass(frozen=True)
class Proposal:
    case: CaseKey
    disposition: Disposition
    summary: str
    claims: tuple[Claim, ...]
    policy: PolicyDecision
    can_post: bool


@dataclass(frozen=True)
class GraphRun:
    investigation: Investigation
    reconciliation: Reconciliation
    policy: PolicyDecision
    proposal: Proposal


def investigator(case: CaseKey, tools: ReadOnlyODataTools) -> Investigation:
    """Gather the documents required for a purchase-order item."""
    purchase_order = tools.get_A_PurchaseOrder(case.purchase_order)
    purchase_order_item = tools.get_A_PurchaseOrderItem(
        case.purchase_order, case.purchase_order_item
    )
    goods_receipts: tuple[AMaterialDocumentEntry, ...] = ()
    if purchase_order_item.GoodsReceiptIsExpected:
        goods_receipts = tools.list_A_MaterialDocumentItem(
            case.purchase_order, case.purchase_order_item
        )
    invoices = tools.list_A_SupplierInvoiceItemPurOrdRef(
        case.purchase_order, case.purchase_order_item
    )
    return Investigation(
        case=case,
        purchase_order=purchase_order,
        purchase_order_item=purchase_order_item,
        goods_receipts=goods_receipts,
        invoices=invoices,
        tool_calls=tools.tool_calls,
    )


def reconciler(investigation: Investigation) -> Reconciliation:
    """Compare gathered documents. This node intentionally accepts no tools."""
    item = investigation.purchase_order_item
    purchase_order_amount = item.NetPriceAmount
    original_grs = tuple(
        gr for gr in investigation.goods_receipts if gr.GoodsMovementType == "101"
    )
    original_invoices = tuple(iv for iv in investigation.invoices if iv.ReverseDocument is None)

    goods_receipt_amount = (
        sum((gr.Amount for gr in original_grs), Decimal("0"))
        if item.GoodsReceiptIsExpected
        else None
    )
    invoice_amount = sum(
        (invoice.SupplierInvoiceItemAmount for invoice in original_invoices), Decimal("0")
    )
    goods_receipt_variance = (
        goods_receipt_amount - purchase_order_amount if goods_receipt_amount is not None else None
    )
    invoice_variance = invoice_amount - purchase_order_amount

    claims: list[Claim] = [
        Claim(
            text=f"PO item net amount is {purchase_order_amount} {item.DocumentCurrency}.",
            evidence=(
                EvidenceHandle(
                    kind="purchase_order_item",
                    key=f"{item.PurchaseOrder}/{item.PurchaseOrderItem}",
                ),
            ),
        ),
        Claim(
            text=f"Invoice amount totals {invoice_amount} {item.DocumentCurrency}.",
            evidence=tuple(
                EvidenceHandle(kind="supplier_invoice", key=invoice.SupplierInvoice)
                for invoice in original_invoices
            ),
        ),
    ]
    if goods_receipt_amount is not None:
        claims.append(
            Claim(
                text=f"Goods receipt amount totals {goods_receipt_amount} {item.DocumentCurrency}.",
                evidence=tuple(
                    EvidenceHandle(kind="material_document", key=gr.MaterialDocument)
                    for gr in original_grs
                ),
            )
        )
    else:
        claims.append(
            Claim(
                text="Goods receipt is not expected for this purchase-order item.",
                evidence=(
                    EvidenceHandle(
                        kind="purchase_order_item",
                        key=f"{item.PurchaseOrder}/{item.PurchaseOrderItem}",
                    ),
                ),
            )
        )

    return Reconciliation(
        case=investigation.case,
        claims=tuple(claims),
        purchase_order_amount=purchase_order_amount,
        goods_receipt_expected=item.GoodsReceiptIsExpected,
        goods_receipt_count=len(original_grs),
        invoice_count=len(original_invoices),
        goods_receipt_amount=goods_receipt_amount,
        invoice_amount=invoice_amount,
        goods_receipt_variance=goods_receipt_variance,
        invoice_variance=invoice_variance,
    )


def policy_gate(reconciliation: Reconciliation) -> PolicyDecision:
    """Deterministic policy gate. No model call belongs in this node."""
    return evaluate_policy(
        PolicyInput(
            purchase_order_amount=reconciliation.purchase_order_amount,
            goods_receipt_expected=reconciliation.goods_receipt_expected,
            goods_receipt_count=reconciliation.goods_receipt_count,
            invoice_count=reconciliation.invoice_count,
            goods_receipt_variance=reconciliation.goods_receipt_variance,
            invoice_variance=reconciliation.invoice_variance,
        )
    )


def proposer(reconciliation: Reconciliation, policy: PolicyDecision) -> Proposal:
    """Emit a proposal object only; this is not an ERP write path."""
    disposition = policy.allowed_dispositions[0]
    summary = (
        "Documents reconcile within policy; propose posting for human approval."
        if disposition == "propose_post"
        else "Documents do not reconcile exactly; keep the item in review."
    )
    return Proposal(
        case=reconciliation.case,
        disposition=disposition,
        summary=summary,
        claims=reconciliation.claims,
        policy=policy,
        can_post=False,
    )


def run_case(case: CaseKey, tools: ReadOnlyODataTools | None = None) -> GraphRun:
    """Run the minimal four-node graph for one case."""
    tool_facade = tools or ReadOnlyODataTools()
    investigation = investigator(case, tool_facade)
    reconciliation = reconciler(investigation)
    policy = policy_gate(reconciliation)
    proposal = proposer(reconciliation, policy)
    return GraphRun(
        investigation=investigation,
        reconciliation=reconciliation,
        policy=policy,
        proposal=proposal,
    )
