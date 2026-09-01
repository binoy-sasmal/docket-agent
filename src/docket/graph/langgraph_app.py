"""LangGraph-backed orchestration for invoice-exception investigations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, NotRequired, TypedDict, cast

from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

try:  # LangGraph 1.x name.
    from langgraph.checkpoint.memory import InMemorySaver
except ImportError:  # pragma: no cover - compatibility with older LangGraph releases.
    from langgraph.checkpoint.memory import MemorySaver as InMemorySaver

from docket.approval import ApprovalRecord, approval_request_for, record_approved_resolution
from docket.memory import SupplierMemoryRecord, SupplierMemoryStore
from docket.policy import PolicyDecision
from docket.tools.injection import InjectionOverlay
from docket.tools.odata import ReadOnlyODataTools

from .skeleton import (
    CaseKey,
    GraphRun,
    Investigation,
    Proposal,
    Reconciliation,
    investigator,
    investigator_agent,
    policy_gate,
    proposer,
    proposer_justification,
    reconciler,
    reconciler_narrative,
)


class DocketGraphState(TypedDict):
    """Short-term state carried by the LangGraph checkpointer."""

    case: CaseKey
    investigation: NotRequired[Investigation]
    reconciliation: NotRequired[Reconciliation]
    policy: NotRequired[PolicyDecision]
    proposal: NotRequired[Proposal]
    graph_run: NotRequired[GraphRun]
    approval_record: NotRequired[SupplierMemoryRecord]


@dataclass(frozen=True)
class DocketLangGraph:
    """Compiled graph plus the memory store side effect it gates."""

    graph: Any
    memory_store: SupplierMemoryStore


def investigator_node(state: DocketGraphState) -> dict[str, Investigation]:
    """Gather documents through the read-only OData tool facade."""
    return {"investigation": investigator(state["case"], ReadOnlyODataTools())}


def reconciler_node(state: DocketGraphState) -> dict[str, Reconciliation]:
    """Reconcile gathered documents. This node intentionally accepts no tools."""
    return {"reconciliation": reconciler(state["investigation"])}


def policy_gate_node(state: DocketGraphState) -> dict[str, PolicyDecision]:
    """Apply deterministic policy through docket.policy, not through LangGraph."""
    return {"policy": policy_gate(state["reconciliation"])}


def proposer_node(state: DocketGraphState) -> dict[str, Proposal | GraphRun]:
    """Emit a proposal object only; no side effect happens in this node."""
    proposal = proposer(state["reconciliation"], state["policy"])
    return {
        "proposal": proposal,
        "graph_run": GraphRun(
            investigation=state["investigation"],
            reconciliation=state["reconciliation"],
            policy=state["policy"],
            proposal=proposal,
        ),
    }


def _investigator_node_for(
    model: BaseChatModel, overlays: tuple[InjectionOverlay, ...] = ()
) -> Any:
    def investigator_node_with_model(state: DocketGraphState) -> dict[str, Investigation]:
        tools = ReadOnlyODataTools(overlays=overlays)
        return {"investigation": investigator_agent(state["case"], tools, model)}

    return investigator_node_with_model


def _reconciler_node_for(model: BaseChatModel) -> Any:
    def reconciler_node_with_model(state: DocketGraphState) -> dict[str, Reconciliation]:
        reconciliation = reconciler(state["investigation"])
        narrative = reconciler_narrative(reconciliation, model)
        return {"reconciliation": replace(reconciliation, narrative=narrative)}

    return reconciler_node_with_model


def _proposer_node_for(model: BaseChatModel) -> Any:
    def proposer_node_with_model(state: DocketGraphState) -> dict[str, Proposal | GraphRun]:
        reconciliation, policy = state["reconciliation"], state["policy"]
        proposal = replace(
            proposer(reconciliation, policy),
            summary=proposer_justification(reconciliation, policy, model),
        )
        return {
            "proposal": proposal,
            "graph_run": GraphRun(
                investigation=state["investigation"],
                reconciliation=reconciliation,
                policy=policy,
                proposal=proposal,
            ),
        }

    return proposer_node_with_model


def _coerce_approval(value: object) -> ApprovalRecord:
    if not isinstance(value, dict):
        raise TypeError("approval interrupt must resume with a JSON object")
    return ApprovalRecord(
        approved=bool(value.get("approved")),
        approved_by=str(value.get("approved_by", "")),
        proposed_by=str(value.get("proposed_by", "agent")),
        reason=str(value.get("reason", "")),
    )


def _approval_node_for(
    memory_store: SupplierMemoryStore,
) -> Any:
    def approval_node(state: DocketGraphState) -> dict[str, SupplierMemoryRecord]:
        proposal = state["proposal"]
        approval = _coerce_approval(interrupt(asdict(approval_request_for(proposal))))
        return {
            "approval_record": record_approved_resolution(
                proposal,
                approval,
                memory_store,
            )
        }

    return approval_node


def build_docket_graph(
    *,
    memory_store: SupplierMemoryStore | None = None,
    checkpointer: Any | None = None,
    model: BaseChatModel | None = None,
    overlays: tuple[InjectionOverlay, ...] = (),
) -> DocketLangGraph:
    """Build the real LangGraph app with checkpointing enabled by default.

    With `model=None` (the default), every node is fully deterministic and
    network-free -- this is what the test suite uses, so it stays fast, free
    and reproducible. Pass a chat model (e.g. `docket.llm.get_chat_model()`)
    to put a real LLM in the Investigator, Reconciler and Proposer nodes, per
    docs/PROJECT.md 3.1. `overlays` only take effect on the model path: the
    deterministic nodes never read document free text, so there is nothing
    for an overlay to reach.
    """
    supplier_memory = memory_store or SupplierMemoryStore()
    workflow = StateGraph(DocketGraphState)
    if model is None:
        workflow.add_node("investigator", investigator_node)
        workflow.add_node("reconciler", reconciler_node)
        workflow.add_node("proposer", proposer_node)
    else:
        workflow.add_node("investigator", _investigator_node_for(model, overlays))
        workflow.add_node("reconciler", _reconciler_node_for(model))
        workflow.add_node("proposer", _proposer_node_for(model))
    workflow.add_node("policy_gate", policy_gate_node)
    workflow.add_node("approval", _approval_node_for(supplier_memory))

    workflow.add_edge(START, "investigator")
    workflow.add_edge("investigator", "reconciler")
    workflow.add_edge("reconciler", "policy_gate")
    workflow.add_edge("policy_gate", "proposer")
    workflow.add_edge("proposer", "approval")
    workflow.add_edge("approval", END)

    saver = InMemorySaver() if checkpointer is None else checkpointer
    return DocketLangGraph(graph=workflow.compile(checkpointer=saver), memory_store=supplier_memory)


def run_case_until_approval(
    case: CaseKey,
    *,
    thread_id: str | None = None,
    app: DocketLangGraph | None = None,
) -> dict[str, Any]:
    """Run the graph until the human approval interrupt is reached."""
    docket_graph = app or build_docket_graph()
    config = {"configurable": {"thread_id": thread_id or _thread_id_for(case)}}
    return cast(dict[str, Any], docket_graph.graph.invoke({"case": case}, config=config))


def _thread_id_for(case: CaseKey) -> str:
    return f"{case.purchase_order}/{case.purchase_order_item}"
