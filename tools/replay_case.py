"""Re-run one golden case and print its step-by-step timeline.

For debugging a failed case-run from an eval or a comparison: shows each
node, every model call (with tokens) and every model-requested tool call in
order, then the outcome against the golden label. Content-free, like the
rest of docket.ops: no prompts, notes or answers are printed.

    python tools/replay_case.py 4507000477_00060                     # deterministic
    python tools/replay_case.py 4507000477_00060 --model             # live Groq run
    python tools/replay_case.py 4507000477_00060 --model --overlay   # with its public overlay
"""

from __future__ import annotations

import argparse

from docket import ops
from docket.eval_harness import (
    _case_key,
    _check_citation,
    _check_trajectory,
    _overlays_by_case,
    _run_case,
    load_golden_labels,
)
from docket.tools.injection import InjectionOverlay


def format_timeline(trace: ops.RunTrace) -> list[str]:
    lines = [f"{'offset':>9} {'took':>9}  {'kind':<5} {'node':<13} step"]
    for step in trace.steps:
        tokens = (
            f"  in={step.input_tokens} out={step.output_tokens}"
            if step.kind == "llm" and step.input_tokens is not None
            else ""
        )
        status = "" if step.status == "ok" else f"  ERROR {step.error_type}"
        name = step.model if step.kind == "llm" and step.model else step.name
        lines.append(
            f"{step.started_ms:>7.1f}ms {step.duration_ms:>7.1f}ms  {step.kind:<5} "
            f"{step.node or '-':<13} {name}{tokens}{status}"
        )
    lines.append(
        f"wall {trace.wall_ms:.1f} ms | model calls {trace.llm_calls} | "
        f"tokens {trace.input_tokens + trace.output_tokens} | tool calls {trace.tool_calls}"
    )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_id")
    parser.add_argument("--model", action="store_true", help="live Groq model in the loop")
    parser.add_argument("--overlay", action="store_true", help="apply the case's public overlay")
    args = parser.parse_args()
    if args.overlay and not args.model:
        parser.error("--overlay requires --model: deterministic nodes never read free text")

    labels = {label["case_id"]: label for label in load_golden_labels()}
    if args.case_id not in labels:
        parser.error(f"unknown case {args.case_id!r}; see evals/golden/")
    label = labels[args.case_id]

    model = None
    if args.model:
        from docket.llm import get_chat_model

        model = get_chat_model()
    overlays: tuple[InjectionOverlay, ...] = ()
    if args.overlay:
        entry = _overlays_by_case(include_held_out=False).get(args.case_id)
        if entry is None:
            parser.error(f"case {args.case_id!r} has no public overlay")
        overlays = (entry[0],)

    with ops.record_run() as recorder:
        investigation, proposal = _run_case(_case_key(args.case_id), model, overlays)
    print("\n".join(format_timeline(recorder.finish())))

    trajectory_ok, gaps = _check_trajectory(label, investigation)
    print(f"disposition: {proposal.disposition} (expected {label['expected_disposition']})")
    print(f"trajectory: {'ok' if trajectory_ok else 'gaps: ' + '; '.join(gaps)}")
    if overlays:
        cited, missing = _check_citation(label, proposal.summary)
        print(f"evidence keys cited: {'all' if cited else 'missing ' + ', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
