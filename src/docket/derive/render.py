"""Render selected BPIC 2019 cases into RenderedLineItem documents.

Per docs/DERIVATION.md sections 1.10, 3.2 and 3.3:

- Document identity: every synthetic document key (MaterialDocument,
  SupplierInvoice) is derived directly from the raw log's `eventID` column,
  never invented from scratch -- this keeps every rendered document
  traceable back to a specific raw row, which is what handcheck.py relies
  on and what makes the hand-check gate meaningful.
- Money: the case-level total order value is read once from "Cumulative net
  worth (EUR)" (log-derived). For a case with exactly one GR and one
  invoice, both take that total directly (also log-derived, matching the
  reconnaissance finding that GR value == invoice value in every clean case
  sampled). For a case with more than one GR or more than one invoice, the
  total is split evenly across the documents of that type (authored -- no
  per-document signal exists in the log).
- Reversals (Cancel Goods Receipt / Cancel Invoice Receipt) are matched
  LIFO to the most recent not-yet-reversed original of the same type, and
  copy that original's amount and provenance. The log carries no reference
  field for this either -- it is an authored inference, same as the
  positional GR/invoice matching below.
- Positional GR/invoice matching (docs/DERIVATION.md 3.2) is applied only
  to "3-way match, invoice after GR" items (the only category where
  InvoiceIsGoodsReceiptBased is true, per the clean 1:1 mapping confirmed
  in reconnaissance): the k-th invoice references the k-th goods receipt in
  time order. This is tagged as an authored assumption on the invoice
  entry, never silently applied elsewhere.
"""

from __future__ import annotations

from datetime import UTC
from decimal import Decimal
from pathlib import Path

import pandas as pd

from docket.manifest import write_manifest
from docket.schema.canonical import write_canonical_json
from docket.schema.procurement import (
    ActingUser,
    AMaterialDocumentEntry,
    APurchaseOrder,
    APurchaseOrderItem,
    ASupplierInvoiceEntry,
    RenderedLineItem,
)
from docket.schema.provenance import (
    DEFAULT_GROUP_PROVENANCE,
    FIELD_GROUP_DOCUMENT_AMOUNT,
    Provenance,
)

GR_RECORD = "Record Goods Receipt"
GR_CANCEL = "Cancel Goods Receipt"
IR_RECORD = "Record Invoice Receipt"
IR_CANCEL = "Cancel Invoice Receipt"
PO_CREATE = "Create Purchase Order Item"
PR_CREATE = "Create Purchase Requisition Item"

GR_BASED_IV_CATEGORY = "3-way match, invoice after GR"
"""The only Item Category where InvoiceIsGoodsReceiptBased is true (clean
1:1 mapping, docs/DERIVATION.md 1.11) -- positional GR/invoice matching
(section 3.2) applies only here.
"""


def _acting_user(user_id: str) -> ActingUser:
    return ActingUser(user_id=user_id, is_batch_user=user_id.startswith("batch_"))


def _case_total_amount(trace: pd.DataFrame) -> Decimal:
    """The case's log-derived total order value (docs/DERIVATION.md 1.10):
    the "Cumulative net worth (EUR)" value at the case's earliest event.
    For the 98.2% of cases where the field is constant throughout, this is
    simply that constant. For the rest, it is the value before any
    Change Price event -- i.e. the original order value, per the recorded
    decision.
    """
    col = "event Cumulative net worth (EUR)"
    first_value = trace.sort_values("event time:timestamp")[col].iloc[0]
    return Decimal(str(first_value))


class _DocumentKeyBuilder:
    """Deterministic synthetic document keys, always derived from a raw
    eventID so every rendered document is traceable back to one row.
    """

    @staticmethod
    def material_document(event_id: int) -> str:
        return f"MD{event_id}"

    @staticmethod
    def supplier_invoice(event_id: int) -> str:
        return f"SI{event_id}"

    @staticmethod
    def supplier_invoice_id_by_party(event_id: int) -> str:
        """Surrogate: no field in the log carries the supplier's own invoice
        number distinct from our internal key (docs/DERIVATION.md section
        3). Tagged Provenance.SURROGATE wherever it is exposed for
        inspection; not claimed as log-derived.
        """
        return f"INV-{event_id}"


def _build_header(trace: pd.DataFrame, purchase_order: str) -> APurchaseOrder:
    creation = trace[trace["event concept:name"].isin([PO_CREATE, PR_CREATE])]
    creation = creation.sort_values("event time:timestamp")
    first = creation.iloc[0]

    company = str(trace["case Company"].iloc[0])
    vendor = str(trace["case Vendor"].iloc[0])
    doc_type = str(trace["case Document Type"].iloc[0])

    return APurchaseOrder(
        PurchaseOrder=purchase_order,
        CompanyCode=company,
        PurchaseOrderType=doc_type,
        Supplier=vendor,
        DocumentCurrency="EUR",
        # The log carries no timezone. Treating timestamps as UTC is a
        # documented convention (docs/DERIVATION.md 3.1), not a claim
        # about the source system's actual timezone -- but it must be
        # applied via replace(), not astimezone(), which would silently
        # pick up whatever timezone the rendering machine is set to and
        # make the frozen fixture's hash depend on where it was rendered.
        PurchaseOrderDate=first["event time:timestamp"].to_pydatetime().replace(
            tzinfo=UTC
        ),
        CreatedByUser=_acting_user(str(first["event User"])),
    )


def _build_item(
    trace: pd.DataFrame, purchase_order: str, purchase_order_item: str
) -> APurchaseOrderItem:
    category = str(trace["case Item Category"].iloc[0])
    gr_expected = str(trace["case Goods Receipt"].iloc[0]).lower() == "true"
    gr_based_iv = str(trace["case GR-Based Inv. Verif."].iloc[0]).lower() == "true"
    total = _case_total_amount(trace)

    return APurchaseOrderItem(
        PurchaseOrder=purchase_order,
        PurchaseOrderItem=purchase_order_item,
        NetPriceAmount=total,
        DocumentCurrency="EUR",
        GoodsReceiptIsExpected=gr_expected,
        InvoiceIsGoodsReceiptBased=gr_based_iv,
        PurchaseOrderItemCategory=category,
    )


def _split_amount(total: Decimal, n: int) -> list[Decimal]:
    """Split `total` into n parts summing exactly back to total (the last
    part absorbs any remainder from integer-cent division), n >= 1.
    """
    if n <= 0:
        return []
    cents_total = total.scaleb(2).to_integral_value()
    base = cents_total // n
    remainder = cents_total - base * n
    parts = [base] * n
    parts[-1] += remainder
    return [Decimal(p).scaleb(-2) for p in parts]


def _build_goods_receipts(
    trace: pd.DataFrame, purchase_order: str, purchase_order_item: str, total: Decimal
) -> tuple[AMaterialDocumentEntry, ...]:
    records = trace[trace["event concept:name"] == GR_RECORD].sort_values(
        "event time:timestamp"
    )
    cancels = trace[trace["event concept:name"] == GR_CANCEL].sort_values(
        "event time:timestamp"
    )

    n = len(records)
    provenance = Provenance.LOG_DERIVED if n <= 1 else Provenance.AUTHORED
    amounts = _split_amount(total, n) if n else []

    entries: list[AMaterialDocumentEntry] = []
    open_stack: list[AMaterialDocumentEntry] = []

    for (_, row), amount in zip(records.iterrows(), amounts, strict=True):
        entry = AMaterialDocumentEntry(
            MaterialDocumentYear=str(row["event time:timestamp"].year),
            MaterialDocument=_DocumentKeyBuilder.material_document(int(row["eventID "])),
            MaterialDocumentItem="0001",
            GoodsMovementType="101",
            DocumentDate=row["event time:timestamp"].to_pydatetime().replace(tzinfo=UTC),
            PostingDate=row["event time:timestamp"].to_pydatetime().replace(tzinfo=UTC),
            CreatedByUser=_acting_user(str(row["event User"])),
            PurchaseOrder=purchase_order,
            PurchaseOrderItem=purchase_order_item,
            Amount=amount,
            AmountProvenance=provenance,
        )
        entries.append(entry)
        open_stack.append(entry)

    for _, row in cancels.iterrows():
        reversed_entry = open_stack.pop() if open_stack else None
        entry = AMaterialDocumentEntry(
            MaterialDocumentYear=str(row["event time:timestamp"].year),
            MaterialDocument=_DocumentKeyBuilder.material_document(int(row["eventID "])),
            MaterialDocumentItem="0001",
            GoodsMovementType="102",
            DocumentDate=row["event time:timestamp"].to_pydatetime().replace(tzinfo=UTC),
            PostingDate=row["event time:timestamp"].to_pydatetime().replace(tzinfo=UTC),
            CreatedByUser=_acting_user(str(row["event User"])),
            PurchaseOrder=purchase_order,
            PurchaseOrderItem=purchase_order_item,
            ReversesMaterialDocument=(
                reversed_entry.MaterialDocument if reversed_entry else None
            ),
            Amount=reversed_entry.Amount if reversed_entry else Decimal("0"),
            AmountProvenance=(
                reversed_entry.AmountProvenance if reversed_entry else Provenance.SURROGATE
            ),
        )
        entries.append(entry)

    return tuple(entries)


def _build_invoices(
    trace: pd.DataFrame,
    purchase_order: str,
    purchase_order_item: str,
    total: Decimal,
    category: str,
    goods_receipts: tuple[AMaterialDocumentEntry, ...],
) -> tuple[ASupplierInvoiceEntry, ...]:
    records = trace[trace["event concept:name"] == IR_RECORD].sort_values(
        "event time:timestamp"
    )
    cancels = trace[trace["event concept:name"] == IR_CANCEL].sort_values(
        "event time:timestamp"
    )

    n = len(records)
    provenance = Provenance.LOG_DERIVED if n <= 1 else Provenance.AUTHORED
    amounts = _split_amount(total, n) if n else []

    # docs/DERIVATION.md section 3.2: positional matching only for the
    # GR-based-invoice-verification category, only against original (101)
    # GR entries in time order.
    apply_positional_match = category == GR_BASED_IV_CATEGORY
    original_grs = [g for g in goods_receipts if g.GoodsMovementType == "101"]

    entries: list[ASupplierInvoiceEntry] = []
    open_stack: list[ASupplierInvoiceEntry] = []

    for idx, ((_, row), amount) in enumerate(zip(records.iterrows(), amounts, strict=True)):
        event_id = int(row["eventID "])
        references_material_document = None
        if apply_positional_match and idx < len(original_grs):
            references_material_document = original_grs[idx].MaterialDocument

        entry = ASupplierInvoiceEntry(
            SupplierInvoice=_DocumentKeyBuilder.supplier_invoice(event_id),
            FiscalYear=str(row["event time:timestamp"].year),
            SupplierInvoiceItem="000001",
            CompanyCode=str(trace["case Company"].iloc[0]),
            DocumentDate=row["event time:timestamp"].to_pydatetime().replace(tzinfo=UTC),
            PostingDate=row["event time:timestamp"].to_pydatetime().replace(tzinfo=UTC),
            InvoicingParty=str(trace["case Vendor"].iloc[0]),
            SupplierInvoiceIDByInvcgParty=_DocumentKeyBuilder.supplier_invoice_id_by_party(
                event_id
            ),
            PurchaseOrder=purchase_order,
            PurchaseOrderItem=purchase_order_item,
            SupplierInvoiceItemAmount=amount,
            AmountProvenance=provenance,
            DocumentCurrency="EUR",
            ReferencesMaterialDocument=references_material_document,
        )
        entries.append(entry)
        open_stack.append(entry)

    for _, row in cancels.iterrows():
        reversed_entry = open_stack.pop() if open_stack else None
        event_id = int(row["eventID "])
        entry = ASupplierInvoiceEntry(
            SupplierInvoice=_DocumentKeyBuilder.supplier_invoice(event_id),
            FiscalYear=str(row["event time:timestamp"].year),
            SupplierInvoiceItem="000001",
            CompanyCode=str(trace["case Company"].iloc[0]),
            DocumentDate=row["event time:timestamp"].to_pydatetime().replace(tzinfo=UTC),
            PostingDate=row["event time:timestamp"].to_pydatetime().replace(tzinfo=UTC),
            InvoicingParty=str(trace["case Vendor"].iloc[0]),
            SupplierInvoiceIDByInvcgParty=_DocumentKeyBuilder.supplier_invoice_id_by_party(
                event_id
            ),
            PurchaseOrder=purchase_order,
            PurchaseOrderItem=purchase_order_item,
            SupplierInvoiceItemAmount=(
                reversed_entry.SupplierInvoiceItemAmount if reversed_entry else Decimal("0")
            ),
            AmountProvenance=(
                reversed_entry.AmountProvenance if reversed_entry else Provenance.SURROGATE
            ),
            DocumentCurrency="EUR",
            ReverseDocument=reversed_entry.SupplierInvoice if reversed_entry else None,
        )
        entries.append(entry)

    return tuple(entries)


def render_case(trace: pd.DataFrame) -> RenderedLineItem:
    """Render one case's raw event rows (already filtered to a single
    `case concept:name`, all columns from load_raw) into a RenderedLineItem.
    """
    case_id = str(trace["case concept:name"].iloc[0])
    purchase_order = str(trace["case Purchasing Document"].iloc[0])
    purchase_order_item = str(trace["case Item"].iloc[0]).zfill(5)
    category = str(trace["case Item Category"].iloc[0])

    header = _build_header(trace, purchase_order)
    item = _build_item(trace, purchase_order, purchase_order_item)
    total = item.NetPriceAmount

    goods_receipts = _build_goods_receipts(trace, purchase_order, purchase_order_item, total)
    invoices = _build_invoices(
        trace, purchase_order, purchase_order_item, total, category, goods_receipts
    )

    n_gr = sum(1 for g in goods_receipts if g.GoodsMovementType == "101")
    n_iv = sum(1 for i in invoices if i.ReverseDocument is None)
    field_group_provenance = dict(DEFAULT_GROUP_PROVENANCE)
    field_group_provenance[FIELD_GROUP_DOCUMENT_AMOUNT] = (
        Provenance.LOG_DERIVED if (n_gr <= 1 and n_iv <= 1) else Provenance.AUTHORED
    )

    return RenderedLineItem(
        source_case_id=case_id,
        purchase_order=header,
        purchase_order_item=item,
        goods_receipts=goods_receipts,
        invoices=invoices,
        field_group_provenance=field_group_provenance,
    )


RENDERED_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "rendered"
RENDERED_MANIFEST_PATH = RENDERED_DIR / "MANIFEST.sha256"


def render_all(df: pd.DataFrame, case_ids: list[str]) -> dict[str, RenderedLineItem]:
    docs: dict[str, RenderedLineItem] = {}
    for case_id in case_ids:
        trace = df[df["case concept:name"] == case_id]
        if trace.empty:
            raise ValueError(f"case_id {case_id!r} not found in the loaded frame")
        docs[case_id] = render_case(trace)
    return docs


def write_rendered(docs: dict[str, RenderedLineItem], directory: Path = RENDERED_DIR) -> str:
    """Write one canonical JSON file per rendered document
    (fixtures/rendered/documents/<case_id>.json -- the filename is exactly
    the source case ID, which is already "<PurchasingDocument>_<Item>" in
    the raw log) and a manifest over the whole directory. Returns the root
    hash. Tier 2, per docs/PROJECT.md section 6.1: committed and
    manifest-pinned, but re-issuable -- re-running this function and
    committing the result is how a schema fix gets applied, as an explicit
    step, never a side effect of something else.
    """
    documents_dir = directory / "documents"
    documents_dir.mkdir(parents=True, exist_ok=True)

    for case_id, doc in docs.items():
        path = documents_dir / f"{case_id}.json"
        write_canonical_json(path, doc.model_dump(mode="python"))

    manifest_path = directory / "MANIFEST.sha256"
    return write_manifest(directory, manifest_path)


if __name__ == "__main__":
    import json

    from docket.derive.load import load_raw
    from docket.derive.sample import DERIVED_SELECTION_PATH

    with DERIVED_SELECTION_PATH.open(encoding="utf-8") as handle:
        selection = json.load(handle)
    case_ids = selection["selected_case_ids"]

    frame = load_raw()
    rendered = render_all(frame, case_ids)
    root = write_rendered(rendered)
    print(f"rendered {len(rendered)} documents to {RENDERED_DIR}")
    print(f"manifest root hash: {root}")
