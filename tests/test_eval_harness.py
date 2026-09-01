"""CI gate for docs/PROJECT.md section 6: disposition accuracy and
trajectory correctness on the frozen Day 3 golden set.

Deterministic mode only -- free, fast, reproducible, no API key. It cannot
gate injection success rate (see docket.eval_harness's module docstring for
why); that number comes from `python tools/run_eval.py --model`, run by a
human, and reported in the README rather than gated here.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from docket.eval_harness import OVERLAY_PATH, load_golden_labels, run_eval
from docket.tools.injection import OverlayNotAuthored

# Never actually invoked: run_eval loads overlays before it runs any case, so
# the unauthored-payload check raises before this model would be called. It
# exists only to get past the "held-out requires a model" guard.
_STUB_MODEL = FakeListChatModel(responses=["unused"])


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


def test_held_out_run_requires_a_model() -> None:
    """A held-out run without a model would measure nothing.

    The deterministic nodes never read document free text, so every overlay
    would be a no-op and the run would report a held-out rate that no attack
    ever produced. Refuse it rather than emit a number.
    """
    with pytest.raises(ValueError, match="requires a model"):
        run_eval(include_held_out=True)


def test_held_out_run_refuses_unauthored_payloads() -> None:
    """The harness must not silently skip placeholder payloads.

    A "final run" that quietly dropped the four held-out attacks would report
    a held-out result that was never measured -- the one failure this metric
    cannot survive (docs/PROJECT.md 6.1). Once the payloads are authored this
    test skips, and `test_every_held_out_overlay_targets_a_golden_case` below
    keeps covering the wiring.
    """
    record = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
    if all("payload" in entry for entry in record["held_out_overlays"]):
        pytest.skip("held-out payloads have been authored")

    with pytest.raises(OverlayNotAuthored):
        run_eval(model=_STUB_MODEL, include_held_out=True)


def test_every_overlay_targets_a_distinct_golden_case() -> None:
    """Each of the eight overlays must land on a case the harness scores.

    An overlay pointing at a case outside the golden 30 would never run, and
    two overlays on one case would mean an attack silently dropped while
    still counted -- `_overlays_by_case` raises on the latter.
    """
    record = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
    golden_case_ids = {label["case_id"] for label in load_golden_labels()}
    targeted = [
        entry["case_id"]
        for entry in record["public_overlays"] + record["held_out_overlays"]
    ]

    assert len(targeted) == len(set(targeted)), "two overlays target the same case"
    assert set(targeted) <= golden_case_ids, "overlay targets a case outside the golden set"


def test_flagged_injection_labels_match_the_overlay_targets() -> None:
    """`is_injection_case` in the labels and the overlay targets are two
    independently authored statements of the same fact. If they drift, one of
    them is wrong and the injection denominator is not what it claims.
    """
    record = json.loads(OVERLAY_PATH.read_text(encoding="utf-8"))
    targeted = {
        entry["case_id"]
        for entry in record["public_overlays"] + record["held_out_overlays"]
    }
    flagged = {
        label["case_id"] for label in load_golden_labels() if label["is_injection_case"]
    }

    assert flagged == targeted
