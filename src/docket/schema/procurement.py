"""Document schema, shaped like SAP OData procurement entities.

Entity and field names follow the public S/4HANA procurement API reference
(API_PURCHASEORDER_PROCESS_SRV, API_MATERIAL_DOCUMENT_SRV,
API_SUPPLIERINVOICE_PROCESS_SRV) -- see docs/DERIVATION.md section 3 for the
full field table and the reasoning behind each modelling choice. These names
were checked against the public API reference, not a live Business
Accelerator Hub tenant (none was available for this project) -- if a name
turns out to be wrong, fixtures/rendered/ is deliberately re-issuable (see
docs/PROJECT.md section 6.1 / AGENTS.md), so re-render rather than editing
JSON by hand.

Money is always decimal.Decimal, never float -- see
docs/DERIVATION.md 1.10 on the source's scientific-notation values, and
schema/canonical.py for how Decimal is serialised.

Every entry that denormalises a SAP header+item pair (goods receipts,
invoices) does so because, within a single rendered line item, a given
material document or supplier invoice header exists for exactly one item --
the normalisation SAP needs across many PO items doesn't apply once the
fixture is split one-file-per-line-item (docs/DERIVATION.md section 3,
"One JSON file per line item").
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from docket.schema.provenance import Provenance

# 101 = goods receipt, 102 = reversal of a goods receipt (cancellation).
# docs/DERIVATION.md section 3.3: cancellations are rendered as reversal
# documents, never as deletions of the original.
GoodsMovementType = Literal["101", "102"]


class _Frozen(BaseModel):
    """Base for every schema model: immutable once constructed, no unknown
    fields silently accepted (typos in field names fail loudly instead of
    disappearing into an unused kwarg).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class ActingUser(_Frozen):
    """Who performed an event. The log distinguishes human users from batch
    users (607 vs 20) -- this is preserved because it is what makes the
    Policy gate's segregation-of-duties check (docs/PROJECT.md section 3.1)
    testable against real data rather than synthetic data.
    """

    user_id: str
    is_batch_user: bool


class APurchaseOrder(_Frozen):
    """A_PurchaseOrder -- the PO header. Built once per Purchasing Document,
    shared by every line item on that document (docs/DERIVATION.md 1.11:
    median 1 item/document, but a long tail runs up to 429).
    """

    PurchaseOrder: str
    CompanyCode: str
    PurchaseOrderType: str
    Supplier: str
    PurchasingOrganization: str | None = None
    PurchasingGroup: str | None = None
    DocumentCurrency: str
    PurchaseOrderDate: datetime
    CreatedByUser: ActingUser


class APurchaseOrderItem(_Frozen):
    """A_PurchaseOrderItem. NetPriceAmount is log-derived per
    docs/DERIVATION.md 1.10 -- pulled from the case's (near-)constant
    "Cumulative net worth (EUR)" value, not authored.

    There is no NetAmount field on the real entity -- verified against a
    community-maintained field mirror of API_PURCHASEORDER_PROCESS_SRV
    during Session 1 (docs/DERIVATION.md section 3) after an earlier draft
    of this schema included one. Only NetPriceAmount and NetPriceQuantity
    exist; since quantities are null in Session 1 (no quantity field in the
    source log), NetPriceAmount here carries the case's whole log-derived
    order value rather than a true per-unit price -- a modelling
    simplification forced by the source data, not a claim about what the
    real field means.
    """

    PurchaseOrder: str
    PurchaseOrderItem: str
    Material: str | None = None
    MaterialGroup: str | None = None
    Plant: str | None = None
    OrderQuantity: Decimal | None = None
    PurchaseOrderQuantityUnit: str | None = None
    NetPriceAmount: Decimal
    DocumentCurrency: str
    GoodsReceiptIsExpected: bool
    InvoiceIsGoodsReceiptBased: bool
    IsCompletelyDelivered: bool | None = None
    IsFinallyInvoiced: bool | None = None
    PurchaseOrderItemCategory: str
    """The BPIC 2019 Item Category value verbatim (one of the four match
    types) -- kept as the category name rather than mapped onto a numeric
    SAP item-category code, since no such mapping is documented and
    inventing one would be exactly the kind of unlabelled fabrication
    AGENTS.md warns against.
    """
    AccountAssignmentCategory: str | None = None


class AMaterialDocumentEntry(_Frozen):
    """A_MaterialDocumentHeader + A_MaterialDocumentItem, denormalised (see
    module docstring). One entry per Record/Cancel Goods Receipt event.
    """

    MaterialDocumentYear: str
    MaterialDocument: str
    MaterialDocumentItem: str
    GoodsMovementType: GoodsMovementType
    DocumentDate: datetime
    PostingDate: datetime
    CreatedByUser: ActingUser
    PurchaseOrder: str
    PurchaseOrderItem: str
    QuantityInEntryUnit: Decimal | None = None
    EntryUnit: str | None = None
    Plant: str | None = None
    ReversesMaterialDocument: str | None = None
    """Set only on a GoodsMovementType 102 reversal entry, pointing back at
    the 101 entry it reverses. docs/DERIVATION.md 3.3.
    """
    Amount: Decimal
    AmountProvenance: Provenance
    """log-derived if this is the only GR on the case (equal to the PO
    item's NetPriceAmount); authored if the case has more than one GR (a
    split of that total -- docs/DERIVATION.md 1.10).
    """


class ASupplierInvoiceEntry(_Frozen):
    """A_SupplierInvoice + A_SupplierInvoiceItemPurOrdRef, denormalised (see
    module docstring). One entry per Record Invoice Receipt event.
    """

    SupplierInvoice: str
    FiscalYear: str
    SupplierInvoiceItem: str
    CompanyCode: str
    DocumentDate: datetime
    PostingDate: datetime
    InvoicingParty: str
    SupplierInvoiceIDByInvcgParty: str
    """The supplier's own invoice number, distinct from the internal
    document number above -- what duplicate-invoice detection would key on
    (deferred past Session 1, but the field is kept: docs/DERIVATION.md
    section 3).
    """
    PurchaseOrder: str
    PurchaseOrderItem: str
    QuantityInPurchaseOrderUnit: Decimal | None = None
    SupplierInvoiceItemAmount: Decimal
    AmountProvenance: Provenance
    """Same rule as AMaterialDocumentEntry.Amount: log-derived if this is the
    only invoice on the case, authored otherwise.
    """
    DocumentCurrency: str
    PaymentTerms: str | None = None
    ReverseDocument: str | None = None
    """Set only on an entry created from a Cancel Invoice Receipt event,
    pointing back at the invoice it reverses.
    """
    ReferencesMaterialDocument: str | None = None
    """Authored positional-match assumption, set only when
    InvoiceIsGoodsReceiptBased is true and the case has multiple GRs/
    invoices -- docs/DERIVATION.md section 3.2. None for the default
    (unmatched) case.
    """


class RenderedLineItem(_Frozen):
    """The complete rendered document for one BPIC 2019 case (line item):
    PO header, PO item, every goods-receipt and invoice document
    reconstructed from the event sequence, plus source traceability and
    field-group provenance. This is what gets written as one JSON file per
    line item (docs/DERIVATION.md section 3).
    """

    source_case_id: str
    """The case concept:name from the raw log -- e.g. "4507004931_00020" --
    kept verbatim so any rendered document can be traced back to its raw
    event rows (this is what handcheck.py cross-references).
    """
    purchase_order: APurchaseOrder
    purchase_order_item: APurchaseOrderItem
    goods_receipts: tuple[AMaterialDocumentEntry, ...]
    invoices: tuple[ASupplierInvoiceEntry, ...]
    field_group_provenance: dict[str, Provenance]
    """docs/DERIVATION.md 3.1 / schema/provenance.py -- one entry per field
    group name, not per individual field.
    """
