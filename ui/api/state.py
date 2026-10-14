"""Runtime state for the web UI: compiled graphs, runs, case catalogue.

By default every piece of workflow state lives in one SQLite file
(`DOCKET_UI_STATE_DB`, default `data/runtime/docket-ui.sqlite`): LangGraph's
checkpoints, supplier memory with its audit trail (both via
`docket.durable`), and the UI's own run records. A run paused at the approval
`interrupt()` therefore survives a server restart and can be approved by the
next process, and a decision recorded before the restart is still refused a
second time after it.

All three are durable together, or none is. A durable checkpointer under a
volatile memory store would let a resume succeed while the approved write it
produced evaporated; durable graph state with volatile run records would leave
paused threads that no screen can reach. Set `DOCKET_UI_STATE_DB=memory` for
the old process-local behaviour, which the UI then states plainly.

Run a single worker either way. SQLite serialises writers, but the compiled
graph cache and run lock are per process, and multi-worker operation has not
been tested.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from docket.durable import CHECKPOINT_TYPES, open_durable_state
from docket.eval_harness import GOLDEN_DIR, load_golden_labels
from docket.fixture_store import FrozenFixtureStore
from docket.graph.langgraph_app import DocketLangGraph, build_docket_graph
from docket.graph.skeleton import CaseKey
from docket.memory import SupplierMemory, SupplierMemoryStore
from docket.tools.injection import InjectionOverlay, load_public_overlays

RunMode = Literal["deterministic", "live"]
RunStatus = Literal["awaiting_approval", "approved", "rejected"]

_MEMORY_SENTINEL = "memory"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _state_db_setting() -> str:
    return os.environ.get(
        "DOCKET_UI_STATE_DB", str(repo_root() / "data" / "runtime" / "docket-ui.sqlite")
    )


class _RunStore:
    """Run records, in memory or in the shared SQLite file.

    A cache in front of the table: every write goes through `save`, which
    persists before returning, so the table is never behind what the API has
    told a client.
    """

    def __init__(self, path: Path | None) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._conn: sqlite3.Connection | None = None
        if path is not None:
            self._conn = sqlite3.connect(str(path), check_same_thread=False)
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS ui_runs "
                "(run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, record TEXT NOT NULL)"
            )
            self._conn.commit()
            for (blob,) in self._conn.execute("SELECT record FROM ui_runs"):
                record = _record_from_json(blob)
                self._runs[record.run_id] = record

    def save(self, record: RunRecord) -> None:
        if self._conn is not None:
            self._conn.execute(
                "INSERT INTO ui_runs (run_id, created_at, record) VALUES (?, ?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET record = excluded.record",
                (record.run_id, record.created_at, _record_to_json(record)),
            )
            self._conn.commit()
        self._runs[record.run_id] = record

    def get(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def all(self) -> list[RunRecord]:
        return list(self._runs.values())


def _open_state() -> tuple[Any, SupplierMemory, _RunStore, Path | None]:
    setting = _state_db_setting()
    if setting == _MEMORY_SENTINEL:
        # Same allowlist as the durable path: checkpoint revival is the one
        # place a serialized payload turns back into Python objects.
        checkpointer = InMemorySaver(
            serde=JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_TYPES)
        )
        return checkpointer, SupplierMemoryStore(), _RunStore(None), None
    path = Path(setting)
    path.parent.mkdir(parents=True, exist_ok=True)
    durable = open_durable_state(path)
    return durable.checkpointer, durable.memory_store, _RunStore(path), path


_GRAPHS: dict[tuple[RunMode, str], DocketLangGraph] = {}
_LOCK = threading.Lock()


def persistence() -> dict[str, Any]:
    """What survives a restart, stated from the store actually in use."""
    if _STATE_PATH is None:
        return {
            "durable": False,
            "path": None,
            "note": (
                "Graph checkpoints, supplier memory and run records are in process memory "
                "and are lost when the server stops (DOCKET_UI_STATE_DB=memory)."
            ),
        }
    return {
        "durable": True,
        "path": str(_STATE_PATH),
        "note": (
            "Graph checkpoints, supplier memory with its audit trail, and run records are "
            "stored together in one SQLite file, so a run awaiting approval survives a "
            "restart. Run a single worker."
        ),
    }


class UiError(RuntimeError):
    """A failure with a message that is safe and useful to show a human."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass
class RunRecord:
    """One case run, held from the `interrupt()` until a human decides.

    `proposed_by` is set here, server-side, from what actually produced the
    proposal. It is never accepted from the client: the segregation-of-duties
    check in `docket.approval.record_approved_resolution` compares
    `approved_by` against `proposed_by`, so a client able to supply both could
    send them equal, or send two different strings for the same person, and
    the check would still pass while meaning nothing.
    """

    run_id: str
    case: CaseKey
    mode: RunMode
    overlay_id: str | None
    thread_id: str
    proposed_by: str
    status: RunStatus
    created_at: str
    payload: dict[str, Any]
    decision: dict[str, Any] | None = None


def memory_store() -> SupplierMemory:
    return _MEMORY_STORE


def public_overlays() -> tuple[InjectionOverlay, ...]:
    """The four authored public injection overlays.

    Held-out overlays are deliberately not exposed: `load_held_out_overlays`
    raises `OverlayNotAuthored` until they are written in a separate,
    repo-blind session (docs/PROJECT.md 6.1), and a UI able to fire them early
    would defeat the point of holding them back.
    """
    overlays: tuple[InjectionOverlay, ...] = load_public_overlays(
        GOLDEN_DIR / "injection_overlays.json"
    )
    return overlays


def overlay_by_id(overlay_id: str) -> InjectionOverlay:
    for overlay in public_overlays():
        if overlay.overlay_id == overlay_id:
            return overlay
    raise UiError(f"unknown public overlay {overlay_id!r}", status_code=404)


def _model_for_live_run() -> Any:
    try:
        from docket.llm import get_chat_model
    except ImportError as exc:  # pragma: no cover - defensive
        raise UiError(f"model client unavailable: {exc}", status_code=503) from exc
    try:
        return get_chat_model()
    except RuntimeError as exc:
        # get_chat_model raises this when GROQ_API_KEY is unset. Surface the
        # real message; it already explains what to do about it.
        raise UiError(str(exc), status_code=503) from exc


def graph_for(mode: RunMode, overlay_id: str | None) -> tuple[DocketLangGraph, str]:
    """Get (or lazily build) the compiled graph for this mode and overlay.

    Overlays are a build-time argument to `build_docket_graph`, not a per-run
    one, so each distinct overlay needs its own compiled variant. They also
    only reach the model path: with `model=None` the deterministic nodes never
    read document free text, so there is nothing for an overlay to touch --
    `request_run` refuses that combination rather than silently accepting an
    overlay that would do nothing.

    Returns the graph and the `proposed_by` identity attributable to it.
    """
    key: tuple[RunMode, str] = (mode, overlay_id or "")
    with _LOCK:
        existing = _GRAPHS.get(key)
    if existing is not None:
        return existing, _proposed_by_for(mode, existing)

    if mode == "deterministic":
        graph = build_docket_graph(memory_store=_MEMORY_STORE, checkpointer=_CHECKPOINTER)
    else:
        model = _model_for_live_run()
        overlays = (overlay_by_id(overlay_id),) if overlay_id else ()
        graph = build_docket_graph(
            memory_store=_MEMORY_STORE,
            checkpointer=_CHECKPOINTER,
            model=model,
            overlays=overlays,
        )
        _LIVE_MODEL_NAMES[key] = _model_display_name(model)

    with _LOCK:
        _GRAPHS.setdefault(key, graph)
        graph = _GRAPHS[key]
    return graph, _proposed_by_for(mode, graph)


_LIVE_MODEL_NAMES: dict[tuple[RunMode, str], str] = {}


def _model_display_name(model: Any) -> str:
    return str(getattr(model, "model_name", None) or getattr(model, "model", "unknown"))


def _proposed_by_for(mode: RunMode, graph: DocketLangGraph) -> str:
    if mode == "deterministic":
        return "agent:deterministic"
    for key, name in _LIVE_MODEL_NAMES.items():
        if _GRAPHS.get(key) is graph:
            return f"agent:groq:{name}"
    return "agent:live"


def register_run(record: RunRecord) -> None:
    save_run(record)


def save_run(record: RunRecord) -> None:
    """Persist a new or changed run record. Call after every mutation."""
    with _LOCK:
        _RUN_STORE.save(record)


def get_run(run_id: str) -> RunRecord:
    with _LOCK:
        record = _RUN_STORE.get(run_id)
    if record is None:
        raise UiError(f"unknown run {run_id!r}", status_code=404)
    return record


def list_runs() -> list[RunRecord]:
    with _LOCK:
        return sorted(_RUN_STORE.all(), key=lambda record: record.created_at, reverse=True)


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


# --- Case catalogue --------------------------------------------------------


@dataclass(frozen=True)
class CatalogueEntry:
    """One frozen-selected case, with its golden label if it has one.

    Golden fields are marked as such on the wire and rendered as labels, never
    as agent output: they are the authored ground truth the run is measured
    against (docs/PROJECT.md 6.1), and conflating the two in a UI would be the
    same category of error as an agent grading its own homework.
    """

    case_id: str
    purchase_order: str
    purchase_order_item: str
    supplier: str
    item_category: str
    currency: str
    purchase_order_amount: str
    goods_receipt_count: int
    invoice_count: int
    goods_receipt_expected: bool
    in_golden_set: bool
    golden_disposition: str | None
    golden_reason_code: str | None
    golden_is_injection_case: bool
    public_overlay_id: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "purchase_order": self.purchase_order,
            "purchase_order_item": self.purchase_order_item,
            "supplier": self.supplier,
            "item_category": self.item_category,
            "currency": self.currency,
            "purchase_order_amount": self.purchase_order_amount,
            "goods_receipt_count": self.goods_receipt_count,
            "invoice_count": self.invoice_count,
            "goods_receipt_expected": self.goods_receipt_expected,
            "in_golden_set": self.in_golden_set,
            "golden_disposition": self.golden_disposition,
            "golden_reason_code": self.golden_reason_code,
            "golden_is_injection_case": self.golden_is_injection_case,
            "public_overlay_id": self.public_overlay_id,
        }


_CATALOGUE: tuple[CatalogueEntry, ...] | None = None


def case_catalogue() -> tuple[CatalogueEntry, ...]:
    """Build the catalogue once, from the frozen selection plus golden labels.

    Read-only in both directions: this walks `fixtures/frozen/selection` and
    `fixtures/rendered/documents` through `FrozenFixtureStore`, which has no
    writer methods, and reads `evals/golden/day3_labels.json` through the eval
    harness's own loader.
    """
    global _CATALOGUE
    if _CATALOGUE is not None:
        return _CATALOGUE

    store = FrozenFixtureStore()
    labels_by_case = {label["case_id"]: label for label in load_golden_labels()}
    overlays_by_case = {overlay.case_id: overlay for overlay in public_overlays()}

    entries: list[CatalogueEntry] = []
    for case_id in store.selected_case_ids:
        try:
            document = store.load_case(case_id)
        except LookupError:
            # Frozen-selected but not rendered. Skip rather than invent a row;
            # the freeze pins which cases are in scope, and a missing rendered
            # document is a fixture problem to report, not one to paper over.
            continue
        item = document.purchase_order_item
        label = labels_by_case.get(case_id)
        overlay = overlays_by_case.get(case_id)
        entries.append(
            CatalogueEntry(
                case_id=case_id,
                purchase_order=item.PurchaseOrder,
                purchase_order_item=item.PurchaseOrderItem,
                supplier=document.purchase_order.Supplier,
                item_category=item.PurchaseOrderItemCategory,
                currency=item.DocumentCurrency,
                purchase_order_amount=str(item.NetPriceAmount),
                goods_receipt_count=len(document.goods_receipts),
                invoice_count=len(document.invoices),
                goods_receipt_expected=item.GoodsReceiptIsExpected,
                in_golden_set=label is not None,
                golden_disposition=label["expected_disposition"] if label else None,
                golden_reason_code=label["reason_code"] if label else None,
                golden_is_injection_case=bool(label["is_injection_case"]) if label else False,
                public_overlay_id=overlay.overlay_id if overlay else None,
            )
        )

    _CATALOGUE = tuple(entries)
    return _CATALOGUE


def find_case(purchase_order: str, purchase_order_item: str) -> CatalogueEntry:
    for entry in case_catalogue():
        if (
            entry.purchase_order == purchase_order
            and entry.purchase_order_item == purchase_order_item
        ):
            return entry
    raise UiError(
        f"case {purchase_order}/{purchase_order_item} is not in the frozen selection",
        status_code=404,
    )


def _record_to_json(record: RunRecord) -> str:
    return json.dumps(asdict(record), sort_keys=True)


def _record_from_json(blob: str) -> RunRecord:
    data = json.loads(blob)
    data["case"] = CaseKey(**data["case"])
    return RunRecord(**data)


# One checkpointer, one memory store and one run store for the whole process,
# shared by every compiled graph variant above, so a run started against one
# variant can still be resumed and approved writes land in one namespace.
# Opened last: reloading saved run records on a restart needs RunRecord and
# its JSON reader, both defined above.
_CHECKPOINTER, _MEMORY_STORE, _RUN_STORE, _STATE_PATH = _open_state()
