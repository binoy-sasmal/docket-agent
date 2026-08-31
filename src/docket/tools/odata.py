"""Read-only SAP OData-shaped tools over the frozen fixture selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from docket.fixture_store import FixtureLookupError, FrozenFixtureStore
from docket.schema.procurement import (
    AMaterialDocumentEntry,
    APurchaseOrder,
    APurchaseOrderItem,
    ASupplierInvoiceEntry,
    RenderedLineItem,
)


@dataclass(frozen=True)
class ToolCall:
    """One read-only tool invocation, recorded for trajectory checks."""

    name: str
    arguments: dict[str, str]


class ToolAccessDenied(PermissionError):
    """Raised if code tries to record a non-allowlisted tool."""


class ReadOnlyODataTools:
    """Small SAP-shaped lookup facade for selected fixture documents.

    The method names intentionally mirror SAP entity names without exposing a
    generic filesystem lookup. All methods read from the frozen-selected
    rendered fixture and return immutable pydantic models.
    """

    ALLOWED_TOOL_NAMES: ClassVar[frozenset[str]] = frozenset(
        {
            "get_A_PurchaseOrder",
            "get_A_PurchaseOrderItem",
            "list_A_MaterialDocumentItem",
            "list_A_SupplierInvoiceItemPurOrdRef",
        }
    )

    def __init__(self, store: FrozenFixtureStore | None = None) -> None:
        self._store = store or FrozenFixtureStore()
        self._documents = tuple(
            self._store.load_case(case_id) for case_id in self._store.selected_case_ids
        )
        self._tool_calls: list[ToolCall] = []

    @property
    def tool_calls(self) -> tuple[ToolCall, ...]:
        return tuple(self._tool_calls)

    @property
    def allowed_tool_names(self) -> frozenset[str]:
        return self.ALLOWED_TOOL_NAMES

    def get_A_PurchaseOrder(self, PurchaseOrder: str) -> APurchaseOrder:
        """Return one `A_PurchaseOrder` header by key."""
        self._record("get_A_PurchaseOrder", PurchaseOrder=PurchaseOrder)
        matches = [
            document.purchase_order
            for document in self._documents
            if document.purchase_order.PurchaseOrder == PurchaseOrder
        ]
        if not matches:
            raise FixtureLookupError(f"purchase order {PurchaseOrder!r} not found")
        return matches[0]

    def get_A_PurchaseOrderItem(
        self, PurchaseOrder: str, PurchaseOrderItem: str
    ) -> APurchaseOrderItem:
        """Return one `A_PurchaseOrderItem` by purchase-order and item key."""
        self._record(
            "get_A_PurchaseOrderItem",
            PurchaseOrder=PurchaseOrder,
            PurchaseOrderItem=PurchaseOrderItem,
        )
        return self._find_document(PurchaseOrder, PurchaseOrderItem).purchase_order_item

    def list_A_MaterialDocumentItem(
        self, PurchaseOrder: str, PurchaseOrderItem: str
    ) -> tuple[AMaterialDocumentEntry, ...]:
        """Return material-document items for a purchase-order item."""
        self._record(
            "list_A_MaterialDocumentItem",
            PurchaseOrder=PurchaseOrder,
            PurchaseOrderItem=PurchaseOrderItem,
        )
        return self._find_document(PurchaseOrder, PurchaseOrderItem).goods_receipts

    def list_A_SupplierInvoiceItemPurOrdRef(
        self, PurchaseOrder: str, PurchaseOrderItem: str
    ) -> tuple[ASupplierInvoiceEntry, ...]:
        """Return supplier-invoice PO-reference items for a purchase-order item."""
        self._record(
            "list_A_SupplierInvoiceItemPurOrdRef",
            PurchaseOrder=PurchaseOrder,
            PurchaseOrderItem=PurchaseOrderItem,
        )
        return self._find_document(PurchaseOrder, PurchaseOrderItem).invoices

    def _find_document(self, purchase_order: str, purchase_order_item: str) -> RenderedLineItem:
        for document in self._documents:
            item = document.purchase_order_item
            if (
                item.PurchaseOrder == purchase_order
                and item.PurchaseOrderItem == purchase_order_item
            ):
                return document
        raise FixtureLookupError(
            f"purchase order item {purchase_order!r}/{purchase_order_item!r} not found"
        )

    def _record(self, name: str, **arguments: str) -> None:
        if name not in self.ALLOWED_TOOL_NAMES:
            raise ToolAccessDenied(f"tool {name!r} is not allowlisted for read-only access")
        self._tool_calls.append(ToolCall(name=name, arguments=dict(arguments)))
