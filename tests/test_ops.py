"""AgentOps telemetry (docket.ops): offline, with a scripted LangChain chat model.

The scripted model subclasses LangChain's real BaseChatModel, so callbacks
fire exactly as they would for ChatGroq; nothing touches the network.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool

from docket import ops
from docket.eval_harness import OVERLAY_PATH, _run_case, run_eval
from docket.graph.langgraph_app import build_docket_graph, run_case_until_approval
from docket.graph.skeleton import CaseKey
from docket.tools.injection import load_public_overlays

THREE_WAY_CASE = CaseKey("4507000477", "00060")
USAGE = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}


class ScriptedChat(BaseChatModel):
    """Replays canned responses; every response reports token usage."""

    script: list[AIMessage] = []
    model_name: str = "scripted-model"
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChat:  # type: ignore[override]
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kw: Any
    ) -> ChatResult:
        self.calls += 1
        message = (
            self.script.pop(0)
            if self.script
            else AIMessage(content="Narrative text for the reviewer.", usage_metadata=USAGE)
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


def _model() -> ScriptedChat:
    return ScriptedChat(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "list_A_MaterialDocumentItem", "args": {}, "id": "c1"},
                    {"name": "list_A_SupplierInvoiceItemPurOrdRef", "args": {}, "id": "c2"},
                ],
                usage_metadata=USAGE,
            ),
            AIMessage(content="Evidence gathered.", usage_metadata=USAGE),
        ]
    )


# ------------------------------------------------------------- recording


def test_nothing_is_recorded_outside_a_block() -> None:
    model = _model()
    _run_case(THREE_WAY_CASE, model, ())  # must not fail with no recorder active
    with ops.record_run() as recorder:
        pass
    assert recorder.finish().steps == ()


def test_model_path_records_nodes_model_calls_tools_and_tokens() -> None:
    model = _model()
    with ops.record_run() as recorder:
        _run_case(THREE_WAY_CASE, model, ())
    trace = recorder.finish()

    assert [s.name for s in trace.of_kind("node")] == [
        "investigator",
        "reconciler",
        "policy_gate",
        "proposer",
    ]
    assert trace.llm_calls == model.calls
    assert trace.input_tokens == 100 * model.calls
    assert trace.output_tokens == 20 * model.calls
    assert {s.name for s in trace.of_kind("tool")} == {
        "list_A_MaterialDocumentItem",
        "list_A_SupplierInvoiceItemPurOrdRef",
    }
    assert all(s.node == "investigator" for s in trace.of_kind("tool"))
    # The architecture invariant, observed at run time: the gate makes no model call.
    assert "policy_gate" not in trace.llm_calls_by_node()
    assert set(trace.llm_calls_by_node()) <= {"investigator", "reconciler", "proposer"}
    assert trace.errors == []


def test_trace_contains_no_document_or_model_text() -> None:
    overlay = load_public_overlays(OVERLAY_PATH)[0]
    case_id = overlay.case_id
    case = CaseKey(*case_id.split("_"))
    model = _model()
    with ops.record_run() as recorder:
        _run_case(case, model, (overlay,))
    dumped = json.dumps(recorder.finish().to_dict())
    assert overlay.payload not in dumped
    for fragment in ("Evidence gathered", "Narrative text", overlay.payload[:20]):
        assert fragment not in dumped


def test_a_failing_tool_is_recorded_as_an_error() -> None:
    def broken() -> list[int]:
        raise TimeoutError("upstream timed out")

    tool = StructuredTool.from_function(func=broken, name="list_broken", description="d")
    with ops.record_run() as recorder, pytest.raises(TimeoutError):
        tool.invoke({})
    (step,) = recorder.finish().of_kind("tool")
    assert step.status == "error"
    assert step.error_type == "TimeoutError"
    assert "timed out" not in json.dumps(recorder.finish().to_dict())


def test_langgraph_path_records_graph_nodes_and_treats_the_interrupt_as_a_pause() -> None:
    app = build_docket_graph(model=_model())
    with ops.record_run() as recorder:
        run_case_until_approval(THREE_WAY_CASE, app=app)
    trace = recorder.finish()
    names = [s.name for s in trace.of_kind("node")]
    assert names[:4] == ["investigator", "reconciler", "policy_gate", "proposer"]
    assert "approval" in names
    assert trace.errors == []  # interrupt() is a pause awaiting a human, not a failure
    assert "policy_gate" not in trace.llm_calls_by_node()
    assert trace.llm_calls > 0


# ---------------------------------------------------------- eval harness


def test_deterministic_eval_writes_one_ops_record_per_case(tmp_path) -> None:
    path = tmp_path / "ops.jsonl"
    report = run_eval(ops_path=path)
    records = ops.read_records(path)
    assert len(records) == len(report.results)
    for record in records:
        assert record["model"] == "deterministic"
        assert record["ops"]["llm_calls"] == 0
        assert set(record["ops"]["node_ms"]) == {
            "investigator",
            "reconciler",
            "policy_gate",
            "proposer",
        }
        assert record["outcome"]["disposition_correct"] is True
        assert record["tool_trajectory"]
    summary = ops.summarize(records)
    assert summary.measured == len(records) and summary.reused == 0
    assert summary.wall_ms_p95 is not None and summary.wall_ms_p95 >= summary.wall_ms_p50


# ------------------------------------------------------------ aggregation


def _record(case: str, *, ok: bool = True, tokens: int = 100, ms: float = 10.0) -> dict:
    return {
        "case_id": case,
        "run": "clean",
        "model": "m",
        "outcome": {"disposition_correct": ok, "trajectory_correct": True},
        "ops": {
            "wall_ms": ms,
            "llm_calls": 3,
            "input_tokens": tokens,
            "output_tokens": 0,
            "tool_calls": 2,
            "errors": 0,
            "node_ms": {"investigator": ms},
            "llm_calls_by_node": {"investigator": 3},
            "models": ["m"],
        },
    }


def test_percentile_is_nearest_rank() -> None:
    assert ops.percentile([], 95) is None
    assert ops.percentile([5.0], 95) == 5.0
    assert ops.percentile([float(i) for i in range(1, 101)], 95) == 95.0


def test_cost_needs_explicit_prices() -> None:
    records = [_record("a", tokens=1_000_000)]
    assert ops.summarize(records).estimated_cost_usd is None
    assert ops.summarize(records, ops.Prices(2.0, 8.0)).estimated_cost_usd == 2.0


def test_identical_runs_pass_the_release_gate() -> None:
    runs = [_record("a"), _record("b")]
    assert ops.compare_runs(runs, runs).passed


def test_release_gate_flags_outcome_regressions_and_missing_cases() -> None:
    baseline = [_record("a"), _record("b"), _record("c", ok=False)]
    candidate = [_record("a", ok=False), _record("c")]
    result = ops.compare_runs(baseline, candidate)
    assert not result.passed
    assert "a [clean]: disposition_correct regressed" in result.regressions
    assert "b [clean]: missing from the candidate run" in result.regressions
    assert "c [clean]: disposition_correct fixed" in result.improvements


def test_release_gate_flags_a_newly_successful_injection() -> None:
    base = [{**_record("a"), "run": "inj-1", "outcome": {"injection_succeeded": False}}]
    cand = [{**_record("a"), "run": "inj-1", "outcome": {"injection_succeeded": True}}]
    assert ops.compare_runs(base, cand).regressions == ("a [inj-1]: injection_succeeded regressed",)


def test_release_gate_flags_cost_latency_and_step_budget() -> None:
    baseline = [_record("a", tokens=100, ms=10.0)]
    candidate = [_record("a", tokens=200, ms=30.0)]
    result = ops.compare_runs(baseline, candidate, max_tool_calls=1)
    joined = " | ".join(result.regressions)
    assert "mean tokens per case-run rose 100%" in joined
    assert "p95 case-run latency rose 200%" in joined
    assert "over the step budget of 1" in joined
