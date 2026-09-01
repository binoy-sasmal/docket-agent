"""Run the Day 3 golden eval and print the results table.

Deterministic mode (default) is what CI runs: `pytest` also gates on this
via tests/test_eval_harness.py, but this script is how a human reads the
actual results table (docs/PROJECT.md section 7, gate 7).

    python tools/run_eval.py            # deterministic, free, no API key
    python tools/run_eval.py --model    # live Groq run; needs GROQ_API_KEY,
                                         # also reports injection success rate
"""

from __future__ import annotations

import argparse

from docket.eval_harness import EvalReport, run_eval


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
            f"({report.injection_cases_evaluated} public overlay case(s))"
        )
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
            print(f"- {result.case_id}")
            if result.citation_gaps:
                print(f"    missing evidence keys in summary: {list(result.citation_gaps)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        action="store_true",
        help="Run through a real Groq model instead of the deterministic path.",
    )
    args = parser.parse_args()

    model = None
    if args.model:
        from docket.llm import get_chat_model

        model = get_chat_model()

    report = run_eval(model=model)
    print_report(report)

    has_discrepancy = report.disposition_accuracy < 1.0 or report.trajectory_accuracy < 1.0
    has_injection_success = bool(report.injection_success_rate)
    return 1 if (has_discrepancy or has_injection_success) else 0


if __name__ == "__main__":
    raise SystemExit(main())
