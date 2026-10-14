"""Supplier-namespaced memory records, written only after approval, and the
audit trail of every approval decision.

Two implementations share one contract: `SupplierMemoryStore` here, which is
process-local and is what the frozen eval and the default graph use, and
`docket.durable.SqliteSupplierMemoryStore`, which survives a restart. Both
make the approved write idempotent, because LangGraph re-executes a node from
its start on resume: a process that dies after the memory write but before the
node is checkpointed as finished will run the write again.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol

MemoryKind = Literal["episodic", "semantic", "procedural"]

AuditEventName = Literal[
    "approval_requested",
    "approval_granted",
    "approval_rejected",
    "memory_written",
    "duplicate_approval_ignored",
]


@dataclass(frozen=True)
class SupplierMemoryRecord:
    supplier: str
    kind: MemoryKind
    case_purchase_order: str
    case_purchase_order_item: str
    text: str
    approved_by: str


@dataclass(frozen=True)
class AuditEvent:
    event: AuditEventName
    case_key: str
    actor: str
    detail: dict[str, str] = field(default_factory=dict)
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    # Events that a node replay would otherwise log twice (the approval
    # request is raised again every time the approval node re-executes)
    # carry a key; a second event with the same key is dropped.
    dedupe_key: str | None = None


class SupplierMemory(Protocol):
    def write_approved(
        self,
        record: SupplierMemoryRecord,
        *,
        idempotency_key: str,
        audit: Sequence[AuditEvent],
    ) -> tuple[SupplierMemoryRecord, bool]:
        """Store `record` and its audit events together, once per key.

        Returns the stored record and whether this call created it. A repeat
        call with a key already used stores nothing new and returns the
        original record, which is what makes a replayed approval harmless.
        """
        ...

    def append_audit(self, event: AuditEvent) -> None: ...

    def list_supplier(self, supplier: str) -> tuple[SupplierMemoryRecord, ...]: ...

    def audit_events(self, case_key: str | None = None) -> tuple[AuditEvent, ...]: ...


class SupplierMemoryStore:
    """Process-local implementation of `SupplierMemory`; dies with the process."""

    def __init__(self) -> None:
        self._records_by_supplier: dict[str, list[SupplierMemoryRecord]] = {}
        self._by_key: dict[str, SupplierMemoryRecord] = {}
        self._audit: list[AuditEvent] = []
        self._dedupe_keys: set[str] = set()

    def write_approved(
        self,
        record: SupplierMemoryRecord,
        *,
        idempotency_key: str,
        audit: Sequence[AuditEvent],
    ) -> tuple[SupplierMemoryRecord, bool]:
        existing = self._by_key.get(idempotency_key)
        if existing is not None:
            return existing, False
        self._by_key[idempotency_key] = record
        self._records_by_supplier.setdefault(record.supplier, []).append(record)
        for event in audit:
            self.append_audit(event)
        return record, True

    def append_audit(self, event: AuditEvent) -> None:
        if event.dedupe_key is not None:
            if event.dedupe_key in self._dedupe_keys:
                return
            self._dedupe_keys.add(event.dedupe_key)
        self._audit.append(event)

    def list_supplier(self, supplier: str) -> tuple[SupplierMemoryRecord, ...]:
        return tuple(self._records_by_supplier.get(supplier, ()))

    def audit_events(self, case_key: str | None = None) -> tuple[AuditEvent, ...]:
        return tuple(e for e in self._audit if case_key is None or e.case_key == case_key)
