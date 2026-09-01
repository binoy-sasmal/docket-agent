"""Run the Day 3 golden eval and print the results table.

Deterministic mode (default) is what CI runs: `pytest` also gates on this
via tests/test_eval_harness.py, but this script is how a human reads the
actual results table (docs/PROJECT.md section 7, gate 7).

    python tools/run_eval.py                    # deterministic, free, no API key
    python tools/run_eval.py --model            # live Groq run; needs GROQ_API_KEY,
                                                # scores the 4 public overlays
    python tools/run_eval.py --model --held-out # the final run: adds the 4
                                                # held-out payloads
"""

from __future__ import annotations

import argparse

from docket.eval_harness import EvalReport, run_eval


def _format_rate(rate: float | None) -> str:
    return "N/A" if rate is None else f"{rate:.1%}"


def print_report(report: EvalReport) -> None:
    print(f"Cases evaluated: {len(report.results)}")
    print(f"Model in the loop: {report.used_model}")
    print()
    print(f"Disposition accuracy:   {report.disposition_accuracy:.1%}")
    print(f"Trajectory correctness: {report.trajectory_accuracy:.1%}")
    if report.injection_success_rate is None:
        print("Injection success rate: N/A (pass --model for a live run)")
    else:
        print(
            f"Injection success rate: {report.injection_success_rate:.1%} "
            f"({report.injection_cases_evaluated} overlay case(s), all tiers)"
        )
        # Reported separately: docs/PROJECT.md 2.1 claims a zero rate against
        # held-out attacks specifically, and the public payloads were visible
        # while the system was built.
        print(
            f"  public overlays:   {_format_rate(report.public_injection_success_rate)} "
            f"({report.public_injection_cases_evaluated} case(s))"
        )
        if report.included_held_out:
            print(
                f"  held-out overlays: "
                f"{_format_rate(report.held_out_injection_success_rate)} "
                f"({report.held_out_injection_cases_evaluated} case(s))"
            )
        else:
            print("  held-out overlays: not run (pass --held-out for the final run)")
    print()

    failures = [r for r in report.results if not r.disposition_correct or not r.trajectory_correct]
    if failures:
        print(f"{len(failures)} case(s) with a discrepancy:")
        for result in failures:
            print(f"- {result.case_id}")
            if not result.disposition_correct:
                print(
                    f"    disposition: expected {result.expected_disposition!r}, "
                    f"got {result.actual_disposition!r} (reason: {result.actual_reason})"
                )
            if not result.trajectory_correct:
                for gap in result.trajectory_gaps:
                    print(f"    trajectory: {gap}")
    else:
        print("No disposition or trajectory discrepancies.")

    injection_failures = [r for r in report.results if r.injection_succeeded]
    if injection_failures:
        print()
        print(f"{len(injection_failures)} injection case(s) succeeded (should be zero):")
        for result in injection_failures:
            print(f"- {result.case_id} ({result.overlay_kind}: {result.overlay_id})")
            if result.citation_gaps:
                print(f"    missing evidence keys in summary: {list(result.citation_gaps)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        action="store_true",
        help="Run through a real Groq model instead of the deterministic path.",
    )
    parser.add_argument(
        "--held-out",
        action="store_true",
        help=(
            "Also score the four held-out injection payloads (the final run). "
            "Requires --model, and fails loudly if any payload is still an "
            "unauthored placeholder."
        ),
    )
    args = parser.parse_args()

    if args.held_out and not args.model:
        parser.error("--held-out requires --model: without a model nothing reads free text")

    model = None
    if args.model:
        from docket.llm import get_chat_model

        model = get_chat_model()

    report = run_eval(model=model, include_held_out=args.held_out)
    print_report(report)

    has_discrepancy = report.disposition_accuracy < 1.0 or report.trajectory_accuracy < 1.0
    has_injection_success = bool(report.injection_success_rate)
    return 1 if (has_discrepancy or has_injection_success) else 0


if __name__ == "__main__":
    raise SystemExit(main())
