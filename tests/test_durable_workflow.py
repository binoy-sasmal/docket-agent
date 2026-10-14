"""Durable approval workflow: restart safety, idempotency, and the audit trail.

The claim under test: a case paused at the human-approval interrupt can be
resumed by a different process after the first one has exited, the approved
memory write happens exactly once however many times the approval is replayed,
and every decision leaves an append-only audit record.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from langgraph.types import Command

from docket.approval import ApprovalRejected
from docket.durable import SqliteSupplierMemoryStore, build_durable_docket_graph
from docket.graph.skeleton import CaseKey
from docket.memory import SupplierMemoryStore

CASE = CaseKey("4507000477", "00060")
SUPPLIER = "vendorID_0103"
APPROVE = {
    "approved": True,
    "approved_by": "user_approver",
    "proposed_by": "agent",
    "reason": "reviewed supporting evidence",
}


def _config(thread_id: str = "durable-test") -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}


def _run_in_fresh_process(db: Path, body: str) -> str:
    """Run `body` in a new Python process, so nothing in memory is shared."""
    script = textwrap.dedent(
        f"""
        import json
        from langgraph.types import Command
        from docket.durable import build_durable_docket_graph
        from docket.graph.skeleton import CaseKey
        app = build_durable_docket_graph({str(db)!r})
        config = {{"configurable": {{"thread_id": "restart-test"}}}}
        """
    ) + textwrap.dedent(body)
    done = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=120
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def test_approval_resumes_in_a_new_process_after_the_first_has_exited(tmp_path: Path) -> None:
    db = tmp_path / "docket.sqlite"

    paused = _run_in_fresh_process(
        db,
        """
        result = app.graph.invoke({"case": CaseKey("4507000477", "00060")}, config=config)
        print(json.dumps(result["__interrupt__"][0].value))
        """,
    )
    assert json.loads(paused)["case_key"] == "4507000477/00060"
    assert SqliteSupplierMemoryStore(db).list_supplier(SUPPLIER) == ()

    resumed = _run_in_fresh_process(
        db,
        f"""
        result = app.graph.invoke(Command(resume={APPROVE!r}), config=config)
        print(result["approval_record"].approved_by)
        """,
    )
    assert resumed == "user_approver"

    store = SqliteSupplierMemoryStore(db)
    (record,) = store.list_supplier(SUPPLIER)
    assert record.case_purchase_order == "4507000477"
    events = [e.event for e in store.audit_events("4507000477/00060")]
    assert events == ["approval_requested", "approval_granted", "memory_written"]


def test_replaying_the_approval_from_a_checkpoint_writes_memory_once(tmp_path: Path) -> None:
    app = build_durable_docket_graph(tmp_path / "docket.sqlite")
    app.graph.invoke({"case": CASE}, config=_config())
    first = app.graph.invoke(Command(resume=APPROVE), config=_config())["approval_record"]

    # Re-run the approval node from the checkpoint taken while it was paused:
    # the same thing that happens if the process dies after the memory write
    # but before LangGraph records the node as finished.
    paused = next(s for s in app.graph.get_state_history(_config()) if s.next == ("approval",))
    replayed = app.graph.invoke(Command(resume=APPROVE), config=paused.config)["approval_record"]

    assert replayed == first
    assert app.memory_store.list_supplier(SUPPLIER) == (first,)
    events = [e.event for e in app.memory_store.audit_events("4507000477/00060")]
    assert events.count("memory_written") == 1
    assert events[-1] == "duplicate_approval_ignored"


def test_a_rejected_approval_is_audited_and_writes_nothing(tmp_path: Path) -> None:
    app = build_durable_docket_graph(tmp_path / "docket.sqlite")
    app.graph.invoke({"case": CASE}, config=_config())

    with pytest.raises(ApprovalRejected, match="segregation"):
        app.graph.invoke(Command(resume={**APPROVE, "approved_by": "agent"}), config=_config())

    assert app.memory_store.list_supplier(SUPPLIER) == ()
    (rejected,) = [
        e
        for e in app.memory_store.audit_events("4507000477/00060")
        if e.event == "approval_rejected"
    ]
    assert rejected.actor == "agent"
    assert "segregation" in rejected.detail["why"]


def test_the_audit_log_cannot_be_edited_or_deleted(tmp_path: Path) -> None:
    db = tmp_path / "docket.sqlite"
    app = build_durable_docket_graph(db)
    app.graph.invoke({"case": CASE}, config=_config())
    app.graph.invoke(Command(resume=APPROVE), config=_config())

    raw = sqlite3.connect(db)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        raw.execute("UPDATE audit_events SET actor = 'someone_else'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        raw.execute("DELETE FROM audit_events")
    raw.close()


def test_in_memory_store_keeps_the_same_idempotency_contract() -> None:
    # The default, process-local store is what the frozen eval and the
    # existing tests use; it must behave the same way, only without a file.
    app_store = SupplierMemoryStore()
    from docket.graph.langgraph_app import build_docket_graph

    app = build_docket_graph(memory_store=app_store)
    app.graph.invoke({"case": CASE}, config=_config("in-memory"))
    first = app.graph.invoke(Command(resume=APPROVE), config=_config("in-memory"))
    paused = next(
        s for s in app.graph.get_state_history(_config("in-memory")) if s.next == ("approval",)
    )
    app.graph.invoke(Command(resume=APPROVE), config=paused.config)

    assert app_store.list_supplier(SUPPLIER) == (first["approval_record"],)
