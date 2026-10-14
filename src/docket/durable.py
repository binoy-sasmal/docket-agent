"""Restart-safe workflow state: checkpoints, supplier memory and audit trail in SQLite.

The default graph keeps everything in process memory, which is right for the
frozen eval and wrong for an approval workflow: a case waiting on a human is
lost if the process stops. `build_durable_docket_graph` puts both halves on
disk together -- LangGraph's checkpoints, so a paused `interrupt()` can be
resumed by a later process, and supplier memory with its audit trail, so an
approved write survives too. Making only the checkpoints durable would let a
resume succeed while the approved write it produced evaporated, which is worse
than either all-durable or all-in-memory.

SQLite, not a server: this is a single-node workflow, the property under test
is restart safety rather than concurrency, and the store needs no service in
CI. The memory write and its audit events commit in one transaction; the
checkpoint commits separately, which is why the write is idempotent (see
docket.memory) rather than relying on the two staying in step.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from docket.graph.langgraph_app import DocketLangGraph, build_docket_graph
from docket.graph.skeleton import (
    CaseKey,
    Claim,
    EvidenceHandle,
    GraphRun,
    Investigation,
    Proposal,
    Reconciliation,
)
from docket.memory import AuditEvent, SupplierMemoryRecord
from docket.policy import PolicyDecision
from docket.schema.procurement import (
    ActingUser,
    AMaterialDocumentEntry,
    APurchaseOrder,
    APurchaseOrderItem,
    ASupplierInvoiceEntry,
)
from docket.schema.provenance import Provenance
from docket.tools.injection import InjectionOverlay
from docket.tools.odata import ToolCall

# Every type the graph puts into its state, named explicitly. Checkpoint
# revival is the one place a stored payload turns back into Python objects,
# and LangGraph's permissive default is documented to become strict -- which
# would break resume, the human-approval path, at the worst possible moment.
CHECKPOINT_TYPES = (
    CaseKey,
    Claim,
    EvidenceHandle,
    GraphRun,
    Investigation,
    Proposal,
    Reconciliation,
    PolicyDecision,
    SupplierMemoryRecord,
    ToolCall,
    ActingUser,
    AMaterialDocumentEntry,
    APurchaseOrder,
    APurchaseOrderItem,
    ASupplierInvoiceEntry,
    Provenance,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS supplier_memory (
    id INTEGER PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    supplier TEXT NOT NULL,
    kind TEXT NOT NULL,
    case_purchase_order TEXT NOT NULL,
    case_purchase_order_item TEXT NOT NULL,
    text TEXT NOT NULL,
    approved_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS supplier_memory_by_supplier ON supplier_memory (supplier);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    event TEXT NOT NULL,
    case_key TEXT NOT NULL,
    actor TEXT NOT NULL,
    detail TEXT NOT NULL,
    dedupe_key TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS audit_events_by_case ON audit_events (case_key);

-- Append-only, enforced by the database rather than by convention: an audit
-- trail that the application can rewrite is not one.
CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS supplier_memory_no_update BEFORE UPDATE ON supplier_memory
BEGIN SELECT RAISE(ABORT, 'supplier_memory is append-only'); END;
CREATE TRIGGER IF NOT EXISTS supplier_memory_no_delete BEFORE DELETE ON supplier_memory
BEGIN SELECT RAISE(ABORT, 'supplier_memory is append-only'); END;
"""


class SqliteSupplierMemoryStore:
    """`docket.memory.SupplierMemory` on disk. Survives a restart."""

    def __init__(self, path: str | Path) -> None:
        # Autocommit mode, with explicit transactions where two writes must
        # land together. One connection guarded by a lock: the UI serves
        # requests from a threadpool.
        self._conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def write_approved(
        self,
        record: SupplierMemoryRecord,
        *,
        idempotency_key: str,
        audit: Sequence[AuditEvent],
    ) -> tuple[SupplierMemoryRecord, bool]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT supplier, kind, case_purchase_order, case_purchase_order_item, "
                    "text, approved_by FROM supplier_memory WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if row is not None:
                    self._conn.execute("COMMIT")
                    return SupplierMemoryRecord(*row), False
                self._conn.execute(
                    "INSERT INTO supplier_memory (idempotency_key, supplier, kind, "
                    "case_purchase_order, case_purchase_order_item, text, approved_by) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        idempotency_key,
                        record.supplier,
                        record.kind,
                        record.case_purchase_order,
                        record.case_purchase_order_item,
                        record.text,
                        record.approved_by,
                    ),
                )
                for event in audit:
                    self._insert_audit(event)
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
        return record, True

    def append_audit(self, event: AuditEvent) -> None:
        with self._lock:
            self._insert_audit(event)

    def list_supplier(self, supplier: str) -> tuple[SupplierMemoryRecord, ...]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT supplier, kind, case_purchase_order, case_purchase_order_item, "
                "text, approved_by FROM supplier_memory WHERE supplier = ? ORDER BY id",
                (supplier,),
            ).fetchall()
        return tuple(SupplierMemoryRecord(*row) for row in rows)

    def audit_events(self, case_key: str | None = None) -> tuple[AuditEvent, ...]:
        query = "SELECT event, case_key, actor, detail, at, dedupe_key FROM audit_events"
        params: tuple[str, ...] = ()
        if case_key is not None:
            query += " WHERE case_key = ?"
            params = (case_key,)
        with self._lock:
            rows = self._conn.execute(query + " ORDER BY id", params).fetchall()
        return tuple(
            AuditEvent(
                event=event,
                case_key=key,
                actor=actor,
                detail=json.loads(detail),
                at=at,
                dedupe_key=dedupe,
            )
            for event, key, actor, detail, at, dedupe in rows
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _insert_audit(self, event: AuditEvent) -> None:
        # OR IGNORE only ever skips a repeated dedupe_key: every other column
        # is NOT NULL and supplied, so no other constraint can fire here.
        self._conn.execute(
            "INSERT OR IGNORE INTO audit_events (at, event, case_key, actor, detail, dedupe_key) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.at,
                event.event,
                event.case_key,
                event.actor,
                json.dumps(event.detail, sort_keys=True),
                event.dedupe_key,
            ),
        )


@dataclass(frozen=True)
class DurableState:
    """The checkpointer and memory store over one SQLite file.

    Opened once and shared by every graph built over it: a caller that
    compiles several graph variants (the web UI builds one per mode and
    overlay) needs them all to resume each other's threads and write to one
    supplier namespace.
    """

    checkpointer: Any
    memory_store: SqliteSupplierMemoryStore


def open_durable_state(path: str | Path) -> DurableState:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    return DurableState(
        checkpointer=SqliteSaver(
            conn, serde=JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_TYPES)
        ),
        memory_store=SqliteSupplierMemoryStore(path),
    )


def build_durable_docket_graph(
    path: str | Path,
    *,
    model: BaseChatModel | None = None,
    overlays: tuple[InjectionOverlay, ...] = (),
) -> DocketLangGraph:
    """The same graph as `build_docket_graph`, with every piece of workflow
    state in one SQLite file at `path`. Any process that opens the same file
    can resume a case another process paused."""
    state = open_durable_state(path)
    return build_docket_graph(
        memory_store=state.memory_store,
        checkpointer=state.checkpointer,
        model=model,
        overlays=overlays,
    )
