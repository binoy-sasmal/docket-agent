"""CI gate for docs/PROJECT.md section 6: disposition accuracy and
trajectory correctness on the frozen Day 3 golden set.

Deterministic mode only -- free, fast, reproducible, no API key. It cannot
gate injection success rate (see docket.eval_harness's module docstring for
why); that number comes from `python tools/run_eval.py --model`, run by a
human, and reported in the README rather than gated here.
"""

from __future__ import annotations

from docket.eval_harness import load_golden_labels, run_eval


def test_golden_set_has_thirty_labelled_cases() -> None:
    assert len(load_golden_labels()) == 30


def test_disposition_accuracy_is_100_percent_on_the_golden_set() -> None:
    report = run_eval()

    failures = [r for r in report.results if not r.disposition_correct]
    assert not failures, [
        (r.case_id, r.expected_disposition, r.actual_disposition, r.actual_reason)
        for r in failures
    ]
    assert report.disposition_accuracy == 1.0


def test_trajectory_correctness_is_100_percent_on_the_golden_set() -> None:
    report = run_eval()

    failures = [r for r in report.results if not r.trajectory_correct]
    assert not failures, [(r.case_id, r.trajectory_gaps) for r in failures]
    assert report.trajectory_accuracy == 1.0


def test_deterministic_mode_reports_no_injection_signal() -> None:
    """The deterministic nodes never read document free text, so there is
    nothing an overlay could change -- this is a property of the
    architecture, not a gap in the harness.
    """
    report = run_eval()

    assert report.injection_success_rate is None
    assert report.injection_cases_evaluated == 0
