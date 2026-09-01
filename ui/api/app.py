"""FastAPI surface for the Docket approval and eval views.

Note what is *not* here: there is no endpoint that posts, pays, releases or
clears anything. `docket` has no such capability -- `Proposal.can_post` is
hardcoded `False` in `docket.graph.skeleton.proposer` and is never model-
controlled -- and adding an endpoint whose name implied otherwise would
misrepresent the system even if it did nothing. The single state-changing
route is `POST /api/runs/{run_id}/decision`, which resumes the graph's
approval `interrupt()`; approving records a resolution to supplier memory,
which is a note about a past case, not an ERP write.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from pydantic import BaseModel, Field

from docket.approval import ApprovalRejected, approval_request_for
from docket.graph.skeleton import CaseKey
from docket.llm import DEFAULT_MODEL
from docket.policy import DEFAULT_TOLERANCE_POLICY

from . import evals
from .serialize import (
    serialize_approval_request,
    serialize_investigation,
    serialize_memory_record,
    serialize_policy,
    serialize_proposal,
    serialize_reconciliation,
)
from .state import (
    RunMode,
    RunRecord,
    UiError,
    case_catalogue,
    find_case,
    get_run,
    graph_for,
    list_runs,
    memory_store,
    new_run_id,
    register_run,
    repo_root,
    utc_now,
)

load_dotenv()

app = FastAPI(
    title="Docket approval and eval views",
    description=__doc__,
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(UiError)
def _ui_error_handler(_request: Any, exc: UiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message})


# The permission matrix from docs/PROJECT.md 3.1, as data. It is served rather
# than hardcoded in the client so the UI renders the same claim the repository
# makes, and so the wording lives next to the code it describes.
NODE_MATRIX = [
    {
        "node": "Investigator",
        "tools": "Read-only document tools",
        "model": True,
        "rationale": (
            "All untrusted content (invoice notes, free text) enters here and nowhere else."
        ),
    },
    {
        "node": "Reconciler",
        "tools": "None",
        "model": True,
        "rationale": (
            "Structurally cannot act -- it has no tools to be injected into using."
        ),
    },
    {
        "node": "Policy gate",
        "tools": "Deterministic functions",
        "model": False,
        "rationale": (
            "Tolerances, approval limits, segregation of duties. No LLM call in this node, ever."
        ),
    },
    {
        "node": "Proposer",
        "tools": "Emits a proposal object only",
        "model": True,
        "rationale": (
            "The write tool sits behind a LangGraph interrupt() requiring human approval."
        ),
    },
]


@app.get("/api/meta")
def get_meta() -> dict[str, Any]:
    """Static facts about this deployment, for the UI to render honestly."""
    return {
        "can_post": False,
        "can_post_note": (
            "Proposal.can_post is hardcoded False in docket.graph.skeleton.proposer and is "
            "never model-controlled. There is no ERP write path in this system."
        ),
        "persistence_note": (
            "Graph checkpoints (InMemorySaver) and supplier memory are process-local and "
            "are lost when the server stops. Run with a single worker: a resumed "
            "interrupt() must reach the same checkpointer instance that created it."
        ),
        "live_mode_available": bool(os.environ.get("GROQ_API_KEY")),
        "live_model": os.environ.get("GROQ_MODEL", DEFAULT_MODEL),
        "node_matrix": NODE_MATRIX,
        # Read off the live policy object rather than restated in the client,
        # so the UI cannot describe a tolerance rule the code does not apply.
        "tolerance_policy": {
            "absolute_tolerance": str(DEFAULT_TOLERANCE_POLICY.absolute_tolerance),
            "relative_tolerance_bps": DEFAULT_TOLERANCE_POLICY.relative_tolerance_bps,
        },
        "golden_set": evals.golden_set_metadata(),
    }


@app.get("/api/cases")
def get_cases() -> dict[str, Any]:
    entries = case_catalogue()
    return {
        "count": len(entries),
        "golden_count": sum(1 for entry in entries if entry.in_golden_set),
        "cases": [entry.as_dict() for entry in entries],
    }


class RunRequest(BaseModel):
    purchase_order: str = Field(min_length=1)
    purchase_order_item: str = Field(min_length=1)
    mode: RunMode = "deterministic"
    overlay_id: str | None = None


def _run_payload(record: RunRecord) -> dict[str, Any]:
    return {
        "run_id": record.run_id,
        "case_id": f"{record.case.purchase_order}_{record.case.purchase_order_item}",
        "purchase_order": record.case.purchase_order,
        "purchase_order_item": record.case.purchase_order_item,
        "mode": record.mode,
        "overlay_id": record.overlay_id,
        "thread_id": record.thread_id,
        "proposed_by": record.proposed_by,
        "status": record.status,
        "created_at": record.created_at,
        "decision": record.decision,
        **record.payload,
    }


@app.post("/api/runs")
def create_run(request: RunRequest) -> dict[str, Any]:
    """Run one case through the graph, stopping at the approval interrupt."""
    entry = find_case(request.purchase_order, request.purchase_order_item)

    if request.overlay_id and request.mode == "deterministic":
        raise UiError(
            "An injection overlay has nothing to reach in deterministic mode: with no model "
            "in the loop, no node reads document free text, so build_docket_graph does not "
            "apply overlays at all. Select live mode to exercise an overlay.",
            status_code=400,
        )
    if request.overlay_id and request.overlay_id != entry.public_overlay_id:
        raise UiError(
            f"overlay {request.overlay_id!r} does not target case {entry.case_id}",
            status_code=400,
        )

    graph, proposed_by = graph_for(request.mode, request.overlay_id)
    case = CaseKey(request.purchase_order, request.purchase_order_item)
    run_id = new_run_id()
    thread_id = f"ui-{run_id}"

    try:
        result = graph.graph.invoke(
            {"case": case}, config={"configurable": {"thread_id": thread_id}}
        )
    except UiError:
        raise
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim, never smoothed over
        raise UiError(f"{type(exc).__name__}: {exc}", status_code=502) from exc

    interrupts = result.get("__interrupt__")
    if not interrupts:
        # The graph reaching END without an interrupt would mean the approval
        # gate did not fire. That is a safety-relevant anomaly, not something
        # to render as a completed run.
        raise UiError(
            "graph completed without reaching the approval interrupt; refusing to display "
            "a proposal that was never gated",
            status_code=500,
        )

    proposal = result["proposal"]
    payload = {
        "investigation": serialize_investigation(result["investigation"]),
        "reconciliation": serialize_reconciliation(result["reconciliation"]),
        "policy": serialize_policy(result["policy"]),
        "proposal": serialize_proposal(proposal),
        "approval_request": serialize_approval_request(approval_request_for(proposal)),
        "interrupt_payload": dict(interrupts[0].value),
        "golden": {
            "in_golden_set": entry.in_golden_set,
            "expected_disposition": entry.golden_disposition,
            "expected_reason_code": entry.golden_reason_code,
            "is_injection_case": entry.golden_is_injection_case,
        },
    }

    record = RunRecord(
        run_id=run_id,
        case=case,
        mode=request.mode,
        overlay_id=request.overlay_id,
        thread_id=thread_id,
        proposed_by=proposed_by,
        status="awaiting_approval",
        created_at=utc_now(),
        payload=payload,
    )
    register_run(record)
    return _run_payload(record)


@app.get("/api/runs")
def get_runs() -> dict[str, Any]:
    return {
        "runs": [
            {
                "run_id": record.run_id,
                "case_id": f"{record.case.purchase_order}_{record.case.purchase_order_item}",
                "mode": record.mode,
                "overlay_id": record.overlay_id,
                "status": record.status,
                "created_at": record.created_at,
                "disposition": record.payload["proposal"]["disposition"],
            }
            for record in list_runs()
        ]
    }


@app.get("/api/runs/{run_id}")
def get_single_run(run_id: str) -> dict[str, Any]:
    return _run_payload(get_run(run_id))


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    approver: str = Field(min_length=1)
    reason: str = Field(min_length=1)


@app.post("/api/runs/{run_id}/decision")
def decide_run(run_id: str, request: DecisionRequest) -> dict[str, Any]:
    """Resume the graph's approval interrupt with a human decision.

    Approving writes one episodic record to supplier memory. It does not post,
    pay or release anything -- no such path exists.
    """
    record = get_run(run_id)
    if record.status != "awaiting_approval":
        raise UiError(
            f"run {run_id} was already {record.status}; a decision is recorded once",
            status_code=409,
        )

    approver = request.approver.strip()
    reason = request.reason.strip()
    if not approver:
        raise UiError("an approver identity is required", status_code=400)
    if not reason:
        raise UiError("a reason is required; it is recorded with the decision", status_code=400)
    if approver == record.proposed_by:
        # docket.approval.record_approved_resolution enforces this too. It is
        # repeated here so the UI can explain the rule before the graph raises,
        # rather than turning a policy rule into an opaque 500.
        raise UiError(
            f"segregation of duties: the approver must differ from the proposer "
            f"({record.proposed_by!r})",
            status_code=409,
        )

    graph, _ = graph_for(record.mode, record.overlay_id)
    config = {"configurable": {"thread_id": record.thread_id}}
    approved = request.decision == "approve"

    try:
        result = graph.graph.invoke(
            Command(
                resume={
                    "approved": approved,
                    "approved_by": approver,
                    "proposed_by": record.proposed_by,
                    "reason": reason,
                }
            ),
            config=config,
        )
    except ApprovalRejected as exc:
        if approved:
            # An approve that the approval layer still refused. Do not retry
            # and do not mark the run decided -- report what it said.
            raise UiError(f"approval refused: {exc}", status_code=409) from exc
        # A rejection is a legitimate terminal outcome, not a server error:
        # record_approved_resolution raises before touching the memory store,
        # so nothing was written.
        record.status = "rejected"
        record.decision = {
            "decision": "reject",
            "approver": approver,
            "reason": reason,
            "proposed_by": record.proposed_by,
            "decided_at": utc_now(),
            "memory_written": False,
            "detail": str(exc),
        }
        return {
            "run": _run_payload(record),
            "memory_record": None,
            "supplier_memory": _supplier_memory(record.payload["proposal"]["supplier"]),
        }
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim
        raise UiError(f"{type(exc).__name__}: {exc}", status_code=502) from exc

    written = result.get("approval_record")
    record.status = "approved"
    record.decision = {
        "decision": "approve",
        "approver": approver,
        "reason": reason,
        "proposed_by": record.proposed_by,
        "decided_at": utc_now(),
        "memory_written": written is not None,
    }
    return {
        "run": _run_payload(record),
        "memory_record": serialize_memory_record(written) if written is not None else None,
        "supplier_memory": _supplier_memory(record.payload["proposal"]["supplier"]),
    }


def _supplier_memory(supplier: str) -> list[dict[str, Any]]:
    return [serialize_memory_record(r) for r in memory_store().list_supplier(supplier)]


@app.get("/api/memory/{supplier}")
def get_supplier_memory(supplier: str) -> dict[str, Any]:
    return {"supplier": supplier, "records": _supplier_memory(supplier)}


@app.get("/api/eval")
def get_eval(refresh: bool = False) -> dict[str, Any]:
    return {
        "deterministic": evals.deterministic_report(refresh=refresh),
        "golden_set": evals.golden_set_metadata(),
        "live": evals.live_state(),
    }


@app.get("/api/eval/live")
def get_live_eval() -> dict[str, Any]:
    return evals.live_state()


@app.post("/api/eval/live")
def post_live_eval() -> dict[str, Any]:
    if not os.environ.get("GROQ_API_KEY"):
        raise UiError(
            "GROQ_API_KEY is not set, so a live run cannot start. The deterministic "
            "numbers above are unaffected -- they need no key.",
            status_code=503,
        )
    return evals.start_live_run()


# Serve the built client when it exists, so the whole thing runs from one
# process. In development the Vite dev server proxies /api here instead.
_DIST = repo_root() / "ui" / "web" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="client")
