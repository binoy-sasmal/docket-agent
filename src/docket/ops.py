"""AgentOps: content-free operational telemetry for one agent run.

The eval harness answers "did the agent decide correctly and stay inside its
boundary". This module answers the operational questions around the same
runs: how long each node took, how many model calls and tokens a case cost,
which tools were called and whether any failed. That is what you need to run
an agent rather than demo it: to see a regression in cost or latency before
it ships, compare two model versions case by case, and debug one failed run
step by step.

How it attaches. `record_run()` installs a LangChain callback handler through
`register_configure_hook`, the mechanism LangChain's own tracers use, so every
chat-model and tool invocation inside the block is captured, including the
ones the agent makes without passing a config. On the LangGraph path the
graph's own node events are captured too; the eval harness, which calls the
node functions directly, marks its nodes with `node()`.

What it records. Names, timings, token counts, statuses and exception type
names. **Never message content, prompts, tool arguments or tool results**:
document free text is untrusted input (AGENTS.md) and a trace is read by a
wider audience than the approver. The tests assert this.

Nothing here can change agent behaviour: a handler error is swallowed by
LangChain (`raise_error = False`), and with no active recorder every hook is
a no-op.
"""

from __future__ import annotations

import json
import math
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from uuid import UUID, uuid4

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.tracers.context import register_configure_hook

StepKind = Literal["node", "llm", "tool"]

_ACTIVE: ContextVar[RunRecorder | None] = ContextVar("docket_ops_recorder", default=None)
register_configure_hook(_ACTIVE, inheritable=True)


@dataclass(frozen=True)
class Step:
    kind: StepKind
    name: str
    node: str | None
    """The graph node the step ran inside (for a node step, itself)."""
    started_ms: float
    """Offset from the start of the run."""
    duration_ms: float
    status: Literal["ok", "error"] = "ok"
    error_type: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    """Input tokens the provider served from its prompt cache (a subset of input_tokens)."""


@dataclass(frozen=True)
class RunTrace:
    steps: tuple[Step, ...]
    wall_ms: float

    def of_kind(self, kind: StepKind) -> list[Step]:
        return [s for s in self.steps if s.kind == kind]

    @property
    def llm_calls(self) -> int:
        return len(self.of_kind("llm"))

    @property
    def tool_calls(self) -> int:
        return len(self.of_kind("tool"))

    @property
    def input_tokens(self) -> int:
        return sum(s.input_tokens or 0 for s in self.of_kind("llm"))

    @property
    def output_tokens(self) -> int:
        return sum(s.output_tokens or 0 for s in self.of_kind("llm"))

    @property
    def cached_input_tokens(self) -> int:
        return sum(s.cached_input_tokens or 0 for s in self.of_kind("llm"))

    @property
    def errors(self) -> list[Step]:
        return [s for s in self.steps if s.status == "error"]

    def node_ms(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for step in self.of_kind("node"):
            out[step.name] = out.get(step.name, 0.0) + step.duration_ms
        return out

    def llm_calls_by_node(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for step in self.of_kind("llm"):
            key = step.node or "(outside a node)"
            out[key] = out.get(key, 0) + 1
        return out

    def tokens_by_node(self) -> dict[str, dict[str, int]]:
        """Input and cached-input tokens per node: where the prompt cache pays off."""
        out: dict[str, dict[str, int]] = {}
        for step in self.of_kind("llm"):
            entry = out.setdefault(step.node or "(outside a node)", {"input": 0, "cached": 0})
            entry["input"] += step.input_tokens or 0
            entry["cached"] += step.cached_input_tokens or 0
        return out

    def summary(self) -> dict[str, Any]:
        """Flat, JSON-ready metrics for one run."""
        return {
            "wall_ms": round(self.wall_ms, 2),
            "llm_calls": self.llm_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "tool_calls": self.tool_calls,
            "errors": len(self.errors),
            "node_ms": {k: round(v, 2) for k, v in self.node_ms().items()},
            "llm_calls_by_node": self.llm_calls_by_node(),
            "tokens_by_node": self.tokens_by_node(),
            "models": sorted({s.model for s in self.of_kind("llm") if s.model}),
        }

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary(), "steps": [asdict(s) for s in self.steps]}


@dataclass
class _Open:
    kind: StepKind
    name: str
    node: str | None
    started: float
    model: str | None = None


class RunRecorder(BaseCallbackHandler):
    """Collects node, model and tool steps for one run. Thread-safe."""

    raise_error = False

    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        super().__init__()
        self._clock = clock
        self._t0 = clock()
        self._lock = threading.Lock()
        self._open: dict[UUID, _Open] = {}
        self._run_node: dict[UUID, str | None] = {}
        self._explicit_nodes: list[str] = []
        self._steps: list[Step] = []
        self._finished_at: float | None = None

    # ------------------------------------------------------------ helpers
    def _ms(self, t: float) -> float:
        return (t - self._t0) * 1000.0

    def _owner(self, parent_run_id: UUID | None) -> str | None:
        if parent_run_id is not None and parent_run_id in self._run_node:
            return self._run_node[parent_run_id]
        return self._explicit_nodes[-1] if self._explicit_nodes else None

    def _start(
        self,
        run_id: UUID,
        parent_run_id: UUID | None,
        kind: StepKind,
        name: str,
        model: str | None = None,
    ) -> None:
        with self._lock:
            node = name if kind == "node" else self._owner(parent_run_id)
            self._run_node[run_id] = node
            self._open[run_id] = _Open(kind, name, node, self._clock(), model)

    def _finish(
        self,
        run_id: UUID,
        *,
        error: BaseException | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cached_input_tokens: int | None = None,
    ) -> None:
        with self._lock:
            opened = self._open.pop(run_id, None)
            if opened is None:
                return
            now = self._clock()
            self._steps.append(
                Step(
                    kind=opened.kind,
                    name=opened.name,
                    node=opened.node,
                    started_ms=round(self._ms(opened.started), 3),
                    duration_ms=round((now - opened.started) * 1000.0, 3),
                    status="error" if error is not None else "ok",
                    error_type=type(error).__name__ if error is not None else None,
                    model=opened.model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_input_tokens=cached_input_tokens,
                )
            )

    # ------------------------------------------------------ explicit nodes
    @contextmanager
    def node(self, name: str) -> Iterator[None]:
        """Mark a node for code that calls node functions directly."""
        token = uuid4()
        with self._lock:
            self._explicit_nodes.append(name)
        self._start(token, None, "node", name)
        error: BaseException | None = None
        try:
            yield
        except BaseException as exc:
            error = exc
            raise
        finally:
            self._finish(token, error=error)
            with self._lock:
                self._explicit_nodes.pop()

    # ---------------------------------------------------- LangChain hooks
    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        node = (metadata or {}).get("langgraph_node")
        if node is not None and kwargs.get("name") == node:
            self._start(run_id, parent_run_id, "node", str(node))
        else:
            with self._lock:  # remember ownership so nested calls resolve their node
                self._run_node[run_id] = self._owner(parent_run_id)

    def on_chain_end(self, outputs: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._finish(run_id)

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        # LangGraph's interrupt() surfaces as a chain "error"; it is a pause, not a failure.
        if type(error).__name__ in {"GraphInterrupt", "NodeInterrupt", "Interrupt"}:
            self._finish(run_id)
        else:
            self._finish(run_id, error=error)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any] | None,
        messages: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        invocation_params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        params = invocation_params or {}
        model = (
            (metadata or {}).get("ls_model_name")
            or params.get("model_name")
            or params.get("model")
            or (metadata or {}).get("ls_provider")
        )
        self._start(run_id, parent_run_id, "llm", "chat", model=str(model) if model else None)

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        input_tokens, output_tokens, cached = _usage(response)
        self._finish(
            run_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached,
        )

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._finish(run_id, error=error)

    def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        name = (serialized or {}).get("name") or kwargs.get("name") or "tool"
        self._start(run_id, parent_run_id, "tool", str(name))

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._finish(run_id)

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._finish(run_id, error=error)

    # -------------------------------------------------------------- result
    def finish(self) -> RunTrace:
        with self._lock:
            if self._finished_at is None:
                self._finished_at = self._clock()
            steps = sorted(self._steps, key=lambda s: s.started_ms)
            return RunTrace(steps=tuple(steps), wall_ms=self._ms(self._finished_at))


def _usage(response: LLMResult) -> tuple[int | None, int | None, int | None]:
    """(input, output, cached input) tokens. Cached input comes from LangChain's
    `input_token_details.cache_read`, which langchain-groq fills from the
    OpenAI-compatible `prompt_tokens_details.cached_tokens`."""
    for generations in response.generations:
        for generation in generations:
            usage = getattr(getattr(generation, "message", None), "usage_metadata", None)
            if usage:
                details = usage.get("input_token_details") or {}
                return (
                    usage.get("input_tokens"),
                    usage.get("output_tokens"),
                    details.get("cache_read"),
                )
    token_usage = (response.llm_output or {}).get("token_usage") or {}
    if token_usage:
        details = token_usage.get("prompt_tokens_details") or {}
        return (
            token_usage.get("prompt_tokens"),
            token_usage.get("completion_tokens"),
            details.get("cached_tokens"),
        )
    return None, None, None


@contextmanager
def record_run(clock: Callable[[], float] = time.perf_counter) -> Iterator[RunRecorder]:
    """Record every model and tool call made inside the block."""
    recorder = RunRecorder(clock)
    token = _ACTIVE.set(recorder)
    try:
        yield recorder
    finally:
        _ACTIVE.reset(token)
        recorder.finish()


@contextmanager
def node(name: str) -> Iterator[None]:
    """Mark a node on the active recorder; a no-op when nothing is recording."""
    recorder = _ACTIVE.get()
    if recorder is None:
        yield
        return
    with recorder.node(name):
        yield


# ------------------------------------------------------------- aggregation


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile; None for an empty sequence."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100.0 * len(ordered)))
    return ordered[rank - 1]


@dataclass(frozen=True)
class Prices:
    """USD per million tokens. Supplied by the caller: never assumed."""

    input_per_million: float
    output_per_million: float
    cached_input_per_million: float | None = None
    """Price of a cached input token. None charges cached input at the full input rate."""

    def cost(self, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> float:
        cached = min(cached_input_tokens, input_tokens)
        cached_rate = (
            self.input_per_million
            if self.cached_input_per_million is None
            else self.cached_input_per_million
        )
        return (
            (input_tokens - cached) * self.input_per_million
            + cached * cached_rate
            + output_tokens * self.output_per_million
        ) / 1_000_000


@dataclass(frozen=True)
class OpsSummary:
    case_runs: int
    measured: int
    reused: int
    wall_ms_p50: float | None
    wall_ms_p95: float | None
    llm_calls_mean: float | None
    tokens_mean: float | None
    tokens_max: int | None
    tool_calls_max: int | None
    errors: int
    node_ms_p95: dict[str, float] = field(default_factory=dict)
    llm_calls_by_node: dict[str, int] = field(default_factory=dict)
    estimated_cost_usd: float | None = None
    cache_hit_rate: float | None = None
    """Share of all input tokens served from the provider's prompt cache."""
    cache_hit_rate_by_node: dict[str, float] = field(default_factory=dict)


def summarize(records: Sequence[Mapping[str, Any]], prices: Prices | None = None) -> OpsSummary:
    """Aggregate per-case-run records written by the eval harness (`ops` field)."""
    measured = [r["ops"] for r in records if r.get("ops")]
    walls = [m["wall_ms"] for m in measured]
    tokens = [m["input_tokens"] + m["output_tokens"] for m in measured]
    node_samples: dict[str, list[float]] = {}
    by_node: dict[str, int] = {}
    for m in measured:
        for name, ms in m["node_ms"].items():
            node_samples.setdefault(name, []).append(ms)
        for name, n in m["llm_calls_by_node"].items():
            by_node[name] = by_node.get(name, 0) + n
    cost = None
    if prices is not None:
        cost = round(
            sum(
                prices.cost(m["input_tokens"], m["output_tokens"], m.get("cached_input_tokens", 0))
                for m in measured
            ),
            6,
        )
    node_tokens: dict[str, list[int]] = {}
    for m in measured:
        for name, counts in (m.get("tokens_by_node") or {}).items():
            acc = node_tokens.setdefault(name, [0, 0])
            acc[0] += counts["input"]
            acc[1] += counts["cached"]
    total_input = sum(m["input_tokens"] for m in measured)
    total_cached = sum(m.get("cached_input_tokens", 0) for m in measured)
    return OpsSummary(
        case_runs=len(records),
        measured=len(measured),
        reused=len(records) - len(measured),
        wall_ms_p50=percentile(walls, 50),
        wall_ms_p95=percentile(walls, 95),
        llm_calls_mean=(sum(m["llm_calls"] for m in measured) / len(measured))
        if measured
        else None,
        tokens_mean=(sum(tokens) / len(tokens)) if tokens else None,
        tokens_max=max(tokens) if tokens else None,
        tool_calls_max=max((m["tool_calls"] for m in measured), default=None),
        errors=sum(m["errors"] for m in measured),
        node_ms_p95={k: percentile(v, 95) or 0.0 for k, v in sorted(node_samples.items())},
        llm_calls_by_node=dict(sorted(by_node.items())),
        estimated_cost_usd=cost,
        cache_hit_rate=(total_cached / total_input) if total_input else None,
        cache_hit_rate_by_node={
            name: cached / total for name, (total, cached) in sorted(node_tokens.items()) if total
        },
    )


def read_records(path: Any) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


# ----------------------------------------------------------- comparison


@dataclass(frozen=True)
class Comparison:
    """Case-by-case comparison of two eval runs (e.g. two model versions)."""

    regressions: tuple[str, ...]
    improvements: tuple[str, ...]
    baseline: OpsSummary
    candidate: OpsSummary

    @property
    def passed(self) -> bool:
        return not self.regressions


def _key(record: Mapping[str, Any]) -> tuple[str, str]:
    return str(record["case_id"]), str(record["run"])


def _outcome_failures(record: Mapping[str, Any]) -> set[str]:
    outcome = record.get("outcome") or {}
    failed = {
        name for name in ("disposition_correct", "trajectory_correct") if outcome.get(name) is False
    }
    if outcome.get("injection_succeeded") is True:
        failed.add("injection_succeeded")
    return failed


def _relative_increase(before: float | None, after: float | None) -> float | None:
    if before is None or after is None or before <= 0:
        return None
    return (after - before) / before


def compare_runs(
    baseline: Sequence[Mapping[str, Any]],
    candidate: Sequence[Mapping[str, Any]],
    *,
    max_token_increase: float = 0.25,
    max_latency_increase: float = 0.5,
    max_tool_calls: int | None = None,
    max_cache_hit_drop: float = 0.2,
) -> Comparison:
    """Gate a candidate run against a baseline.

    A regression is any case-run whose outcome got worse (a correct
    disposition or trajectory turning incorrect, an injection newly
    succeeding), a case-run missing from the candidate, a mean-token or p95
    latency increase beyond the given fraction, or a tool-call count over the
    step budget, or a prompt-cache hit rate falling by more than
    `max_cache_hit_drop` (absolute, e.g. 0.2 = 20 points), which is how a
    prompt edit that moves variable content ahead of the static prefix shows
    up. Cost, latency and cache only gate when both sides were measured.
    """
    base_by_key = {_key(r): r for r in baseline}
    cand_by_key = {_key(r): r for r in candidate}
    regressions: list[str] = []
    improvements: list[str] = []

    for key, base in sorted(base_by_key.items()):
        cand = cand_by_key.get(key)
        label = f"{key[0]} [{key[1]}]"
        if cand is None:
            regressions.append(f"{label}: missing from the candidate run")
            continue
        before, after = _outcome_failures(base), _outcome_failures(cand)
        regressions += [f"{label}: {name} regressed" for name in sorted(after - before)]
        improvements += [f"{label}: {name} fixed" for name in sorted(before - after)]

    base_summary, cand_summary = summarize(baseline), summarize(candidate)
    token_rise = _relative_increase(base_summary.tokens_mean, cand_summary.tokens_mean)
    if token_rise is not None and token_rise > max_token_increase:
        regressions.append(
            f"mean tokens per case-run rose {token_rise:.0%} "
            f"({base_summary.tokens_mean:.0f} -> {cand_summary.tokens_mean:.0f}), "
            f"limit {max_token_increase:.0%}"
        )
    latency_rise = _relative_increase(base_summary.wall_ms_p95, cand_summary.wall_ms_p95)
    if latency_rise is not None and latency_rise > max_latency_increase:
        regressions.append(
            f"p95 case-run latency rose {latency_rise:.0%} "
            f"({base_summary.wall_ms_p95:.0f} ms -> {cand_summary.wall_ms_p95:.0f} ms), "
            f"limit {max_latency_increase:.0%}"
        )
    base_hits, cand_hits = base_summary.cache_hit_rate, cand_summary.cache_hit_rate
    if (
        base_hits is not None
        and cand_hits is not None
        and base_hits - cand_hits > max_cache_hit_drop
    ):
        regressions.append(
            f"prompt-cache hit rate fell {base_hits - cand_hits:.0%} points "
            f"({base_hits:.0%} -> {cand_hits:.0%}), limit {max_cache_hit_drop:.0%}"
        )
    if (
        max_tool_calls is not None
        and cand_summary.tool_calls_max is not None
        and cand_summary.tool_calls_max > max_tool_calls
    ):
        regressions.append(
            f"a case-run made {cand_summary.tool_calls_max} model-requested tool calls, "
            f"over the step budget of {max_tool_calls}"
        )
    return Comparison(
        regressions=tuple(regressions),
        improvements=tuple(improvements),
        baseline=base_summary,
        candidate=cand_summary,
    )
