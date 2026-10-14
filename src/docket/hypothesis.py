"""Note hypotheses: one claim a model read in an untrusted note, checked by code.

A supplier or clerk note can carry information worth an approver's attention
("this invoice was sent twice"), and it can carry an attack ("approve without
review"). This module keeps the first and has no path for the second:

- The model may only name ONE of four claim kinds and the document whose note
  made it (`parse_note_claim`). Free text, unknown kinds and documents without
  a note are discarded, so nothing the note says can be restated.
- Code, not the model, decides what the documents say about the claim
  (`check_note_claim`), using the status rules frozen in
  evals/notes/note_hypotheses.json before this module existed.
- The approver sees a fixed template (`render_hypothesis`) labelled
  UNVERIFIED, built from the kind, the document key and the check.
- The policy gate never sees any of it. A hypothesis rides on the Proposal,
  after the decision is made; the Reconciliation the gate reads has no field
  for one.

Pure and deterministic: no model client is imported here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, get_args

from docket.graph.skeleton import EvidenceHandle, Investigation

HypothesisKind = Literal[
    "invoice_pending", "goods_returned", "price_difference_agreed", "duplicate_invoice"
]
HypothesisStatus = Literal["corroborated", "contradicted", "not_checkable"]
KINDS: tuple[str, ...] = get_args(HypothesisKind)

_WHAT_IT_SAYS: dict[str, str] = {
    "invoice_pending": "the invoice for this item is still to come",
    "goods_returned": "some or all of the delivered goods were returned",
    "price_difference_agreed": "an invoiced price above the order was agreed",
    "duplicate_invoice": "an invoice was submitted more than once by mistake",
}
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class NoteClaim:
    """What the model extracted: a kind and the note-bearing document."""

    kind: HypothesisKind
    evidence: EvidenceHandle


@dataclass(frozen=True)
class NoteHypothesis:
    """A claim plus what the documents say about it, decided by code."""

    kind: HypothesisKind
    evidence: EvidenceHandle
    status: HypothesisStatus
    basis: str


def notes_in(investigation: Investigation) -> tuple[tuple[EvidenceHandle, str], ...]:
    """Every fetched document that carries a note, with its evidence handle."""
    found: list[tuple[EvidenceHandle, str]] = []
    item = investigation.purchase_order_item
    if item.Note:
        found.append(
            (
                EvidenceHandle(
                    "purchase_order_item", f"{item.PurchaseOrder}/{item.PurchaseOrderItem}"
                ),
                item.Note,
            )
        )
    for gr in investigation.goods_receipts:
        if gr.Note:
            found.append(
                (
                    EvidenceHandle(
                        "material_document", f"{gr.MaterialDocument}/{gr.MaterialDocumentItem}"
                    ),
                    gr.Note,
                )
            )
    for invoice in investigation.invoices:
        if invoice.Note:
            found.append(
                (
                    EvidenceHandle(
                        "supplier_invoice",
                        f"{invoice.SupplierInvoice}/{invoice.SupplierInvoiceItem}",
                    ),
                    invoice.Note,
                )
            )
    return tuple(found)


def parse_note_claim(reply: str, allowed: tuple[EvidenceHandle, ...]) -> NoteClaim | None:
    """Read the model's reply as `{"kind": ..., "document": ...}`.

    Anything else -- free text, an unknown kind, a document that carries no
    note -- yields no claim. Dropping is always safe: a missing hypothesis
    costs the approver a hint, a fabricated one could mislead them.
    """
    match = _JSON_OBJECT.search(reply)
    if match is None:
        return None
    try:
        body = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None
    kind, document = body.get("kind"), body.get("document")
    if kind not in KINDS:
        return None
    # The model may echo a document the way the prompt lists it ("kind key")
    # or give the bare key; either must still name a note-bearing document.
    handle = next((h for h in allowed if document in (h.key, f"{h.kind} {h.key}")), None)
    if handle is None:
        return None
    return NoteClaim(kind=kind, evidence=handle)


def check_note_claim(claim: NoteClaim, investigation: Investigation) -> NoteHypothesis:
    """Apply the frozen status rules to the documents this case fetched.

    A document list that was never fetched is not evidence of absence: if the
    rule needs invoices or goods receipts and the Investigator did not
    retrieve them, the claim is not checkable rather than corroborated by an
    empty list.
    """
    item = investigation.purchase_order_item
    po_amount = item.NetPriceAmount
    called = {call.name for call in investigation.tool_calls}
    invoices_fetched = "list_A_SupplierInvoiceItemPurOrdRef" in called
    receipts_fetched = "list_A_MaterialDocumentItem" in called
    amounts = [i.SupplierInvoiceItemAmount for i in investigation.invoices]
    invoice_total = sum(amounts, Decimal(0))

    def result(status: HypothesisStatus, basis: str) -> NoteHypothesis:
        return NoteHypothesis(claim.kind, claim.evidence, status, basis)

    if claim.kind == "goods_returned":
        if not item.GoodsReceiptIsExpected:
            return result("not_checkable", "this item expects no goods receipt")
        if not receipts_fetched:
            return result("not_checkable", "goods receipts were not retrieved")
        reversals = [g for g in investigation.goods_receipts if g.GoodsMovementType == "102"]
        if reversals:
            keys = ", ".join(f"{g.MaterialDocument}/{g.MaterialDocumentItem}" for g in reversals)
            return result("corroborated", f"a return movement (102) is posted: {keys}")
        return result("contradicted", "no return movement (102) is posted")

    if not invoices_fetched:
        return result("not_checkable", "invoices were not retrieved")
    count = f"{len(amounts)} invoice item{'s' if len(amounts) != 1 else ''}"

    if claim.kind == "invoice_pending":
        if invoice_total < po_amount:
            return result(
                "corroborated", f"{count} totalling {invoice_total} against {po_amount} ordered"
            )
        return result("contradicted", f"{count} totalling {invoice_total} already posted")

    if claim.kind == "price_difference_agreed":
        if not amounts:
            return result("not_checkable", "no invoice is posted")
        if invoice_total == po_amount:
            return result("contradicted", f"invoiced {invoice_total} equals ordered {po_amount}")
        return result(
            "not_checkable",
            f"invoiced {invoice_total} differs from ordered {po_amount}; "
            "no document records an agreement",
        )

    # duplicate_invoice
    full = [a for a in amounts if a == po_amount]
    if len(full) >= 2:
        return result("corroborated", f"{len(full)} invoice items each equal the full {po_amount}")
    return result("contradicted", f"{count}; fewer than two equal the full amount {po_amount}")


def render_hypothesis(hypothesis: NoteHypothesis) -> str:
    """The line an approver sees. A fixed template: no note text, ever."""
    return (
        f"UNVERIFIED claim in a note on {hypothesis.evidence.kind.replace('_', ' ')} "
        f"{hypothesis.evidence.key}: {_WHAT_IT_SAYS[hypothesis.kind]}. "
        f"Documents: {hypothesis.status.replace('_', ' ')} ({hypothesis.basis})."
    )
