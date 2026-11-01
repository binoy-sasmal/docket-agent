"""Release gate: compare two eval runs case by case (e.g. two model versions).

    python tools/run_eval.py --model --ops-out evals/runs/ops-A.jsonl
    GROQ_MODEL=<candidate> python tools/run_eval.py --model --ops-out evals/runs/ops-B.jsonl
    python tools/compare_runs.py evals/runs/ops-A.jsonl evals/runs/ops-B.jsonl

Exits 1 when the candidate regresses: any case-run whose disposition or
trajectory turned incorrect, an injection that newly succeeds, a case-run
missing from the candidate, mean tokens or p95 latency rising past the
limits, or a case-run over the Investigator step budget.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from docket.graph.skeleton import MAX_INVESTIGATOR_TOOL_CALLS
from docket.ops import compare_runs, read_records


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{value:,.1f}" if isinstance(value, float) else str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--max-token-increase", type=float, default=0.25)
    parser.add_argument("--max-latency-increase", type=float, default=0.5)
    args = parser.parse_args()

    baseline, candidate = read_records(args.baseline), read_records(args.candidate)
    result = compare_runs(
        baseline,
        candidate,
        max_token_increase=args.max_token_increase,
        max_latency_increase=args.max_latency_increase,
        max_tool_calls=MAX_INVESTIGATOR_TOOL_CALLS,
    )
    b, c = result.baseline, result.candidate
    rows = (
        (
            "models",
            ", ".join(sorted({r["model"] for r in baseline})),
            ", ".join(sorted({r["model"] for r in candidate})),
        ),
        ("case-runs measured", b.measured, c.measured),
        ("p95 latency (ms)", b.wall_ms_p95, c.wall_ms_p95),
        ("mean tokens", b.tokens_mean, c.tokens_mean),
        ("mean model calls", b.llm_calls_mean, c.llm_calls_mean),
        ("prompt-cache hit rate", b.cache_hit_rate, c.cache_hit_rate),
        ("errors", b.errors, c.errors),
    )
    print(f"{'':<22}{'baseline':>22}{'candidate':>22}")
    for label, before, after in rows:
        print(f"{label:<22}{_fmt(before):>22}{_fmt(after):>22}")
    print()
    for line in result.improvements:
        print(f"improved:  {line}")
    for line in result.regressions:
        print(f"REGRESSED: {line}")
    if result.passed:
        print("PASS: no regressions.")
        return 0
    print(f"FAIL: {len(result.regressions)} regression(s).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
