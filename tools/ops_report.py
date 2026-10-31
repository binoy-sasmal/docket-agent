"""Summarise the operational trace of an eval run written with --ops-out.

    python tools/run_eval.py --ops-out evals/runs/ops-deterministic.jsonl
    python tools/ops_report.py evals/runs/ops-deterministic.jsonl
    python tools/ops_report.py RUN.jsonl --price-in 0.15 --price-out 0.60   # USD per 1M tokens

Prices are never assumed: pass the provider's current per-million-token
prices to get an estimated cost. Content-free by construction (docket.ops).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from docket.ops import OpsSummary, Prices, read_records, summarize


def _fmt(value: float | None, unit: str = "") -> str:
    return "n/a" if value is None else f"{value:,.1f}{unit}"


def render(summary: OpsSummary, models: list[str]) -> str:
    lines = [
        f"Case-runs: {summary.case_runs} ({summary.measured} measured, "
        f"{summary.reused} reused from a resume file and not re-timed)",
        f"Models: {', '.join(models)}",
        f"Latency per case-run: p50 {_fmt(summary.wall_ms_p50, ' ms')}, "
        f"p95 {_fmt(summary.wall_ms_p95, ' ms')}",
        f"Model calls per case-run (mean): {_fmt(summary.llm_calls_mean)}",
        f"Tokens per case-run: mean {_fmt(summary.tokens_mean)}, max {summary.tokens_max}",
        f"Most model-requested tool calls in one case-run: {summary.tool_calls_max}",
        f"Errors: {summary.errors}",
    ]
    if summary.estimated_cost_usd is not None:
        lines.append(f"Estimated cost: ${summary.estimated_cost_usd:.4f}")
    lines.append("p95 time per node:")
    lines += [f"  {name:<13} {ms:,.1f} ms" for name, ms in summary.node_ms_p95.items()]
    lines.append("Model calls by node (total):")
    lines += [f"  {name:<13} {n}" for name, n in summary.llm_calls_by_node.items()]
    if "policy_gate" not in summary.llm_calls_by_node:
        lines.append("  policy_gate   0  (the gate holds no model; see AGENTS.md)")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--price-in", type=float, help="USD per 1M input tokens")
    parser.add_argument("--price-out", type=float, help="USD per 1M output tokens")
    args = parser.parse_args()
    if (args.price_in is None) != (args.price_out is None):
        parser.error("pass both --price-in and --price-out, or neither")
    prices = Prices(args.price_in, args.price_out) if args.price_in is not None else None
    records = read_records(args.path)
    models = sorted({str(r["model"]) for r in records})
    print(render(summarize(records, prices), models))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
