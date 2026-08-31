"""Supplier-namespaced memory records, written only after approval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MemoryKind = Literal["episodic", "semantic", "procedural"]


@dataclass(frozen=True)
class SupplierMemoryRecord:
    supplier: str
    kind: MemoryKind
    case_purchase_order: str
    case_purchase_order_item: str
    text: str
    approved_by: str


class SupplierMemoryStore:
    """A minimal supplier-namespaced memory store.

    This in-memory implementation gives the graph a concrete long-term memory
    contract without introducing persistence policy yet. Writes still flow
    through `docket.approval`.
    """

    def __init__(self) -> None:
        self._records_by_supplier: dict[str, list[SupplierMemoryRecord]] = {}

    def append(self, record: SupplierMemoryRecord) -> None:
        self._records_by_supplier.setdefault(record.supplier, []).append(record)

    def list_supplier(self, supplier: str) -> tuple[SupplierMemoryRecord, ...]:
        return tuple(self._records_by_supplier.get(supplier, ()))
