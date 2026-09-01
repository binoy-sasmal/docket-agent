"""Eval-report access for the dashboard.

The deterministic report is computed by running the real harness
(`docket.eval_harness.run_eval`), never read from a stored results file. The
whole golden 30 takes a few seconds, so there is no reason to cache a number
to disk -- and a stored number is a number that can drift from the code, or be
edited, which is the one thing this project's central claim cannot survive.

The live-model report runs on a background thread. A live run makes several
model calls per case across 30 cases plus the overlay reruns, so it can take
minutes; with a single worker, doing that inside a request would block the
approval view. Its failures are reported verbatim rather than smoothed over:
as of this writing a live run is expected to fail on the free-tier Groq daily
token quota, and a dashboard that rendered a plausible number instead of that
error would be lying.
"""

from __future__ import annotations

import json
import threading
import traceback
from dataclasses import dataclass
from typing import Any, Literal

from docket.eval_harness import GOLDEN_DIR, CaseResult, EvalReport, run_eval

from .state import UiError, utc_now

LiveStatus = Literal["idle", "running", "succeeded", "failed"]

_DETERMINISTIC_REPORT: dict[str, Any] | None = None
_LOCK = threading.Lock()


def serialize_case_result(result: CaseResult) -> dict[str, Any]:
    return {
        "case_id": result.case_id,
        "expected_disposition": result.expected_disposition,
        "actual_disposition": result.actual_disposition,
        "disposition_correct": result.disposition_correct,
        "expected_reason": result.expected_reason,
        "actual_reason": result.actual_reason,
        "trajectory_correct": result.trajectory_correct,
        "trajectory_gaps": list(result.trajectory_gaps),
        "is_injection_case": result.is_injection_case,
        "injection_succeeded": result.injection_succeeded,
        "citation_gaps": list(result.citation_gaps),
        "overlay_id": result.overlay_id,
        "overlay_kind": result.overlay_kind,
    }


def serialize_report(report: EvalReport) -> dict[str, Any]:
    return {
        "results": [serialize_case_result(result) for result in report.results],
        "disposition_accuracy": report.disposition_accuracy,
        "trajectory_accuracy": report.trajectory_accuracy,
        "injection_success_rate": report.injection_success_rate,
        "injection_cases_evaluated": report.injection_cases_evaluated,
        # Public and held-out are carried separately, never pooled for
        # display: docs/PROJECT.md 2.1 claims a zero rate against held-out
        # attacks specifically.
        "public_injection_success_rate": report.public_injection_success_rate,
        "public_injection_cases_evaluated": report.public_injection_cases_evaluated,
        "held_out_injection_success_rate": report.held_out_injection_success_rate,
        "held_out_injection_cases_evaluated": report.held_out_injection_cases_evaluated,
        "included_held_out": report.included_held_out,
        "used_model": report.used_model,
        "case_count": len(report.results),
        "computed_at": utc_now(),
    }


def golden_set_metadata() -> dict[str, Any]:
    """Facts about the frozen eval set itself, read straight from the file.

    Counted at read time rather than hardcoded, so the dashboard cannot claim
    a set size the frozen file does not actually have.
    """
    overlays = json.loads(
        (GOLDEN_DIR / "injection_overlays.json").read_text(encoding="utf-8")
    )
    labels = json.loads((GOLDEN_DIR / "day3_labels.json").read_text(encoding="utf-8"))
    held_out = overlays["held_out_overlays"]
    return {
        "label_count": len(labels["labels"]),
        "labels_status": labels["status"],
        "flagged_injection_cases": sum(
            1 for label in labels["labels"] if label["is_injection_case"]
        ),
        "public_overlay_count": len(overlays["public_overlays"]),
        "held_out_overlay_count": len(held_out),
        "held_out_authored_count": sum(1 for entry in held_out if "payload" in entry),
        "public_overlays": [
            {
                "overlay_id": entry["overlay_id"],
                "case_id": entry["case_id"],
                "target": entry["target"],
                "payload": entry["payload"],
                "success_condition": entry["success_condition"],
            }
            for entry in overlays["public_overlays"]
        ],
        "held_out_overlays": [
            {
                "overlay_id": entry["overlay_id"],
                "case_id": entry["case_id"],
                "target": entry["target"],
                "authored": "payload" in entry,
                "success_condition": entry["success_condition"],
            }
            for entry in held_out
        ],
    }


def deterministic_report(*, refresh: bool = False) -> dict[str, Any]:
    global _DETERMINISTIC_REPORT
    with _LOCK:
        cached = _DETERMINISTIC_REPORT
    if cached is not None and not refresh:
        return cached
    report = serialize_report(run_eval())
    with _LOCK:
        _DETERMINISTIC_REPORT = report
    return report


@dataclass
class LiveRunState:
    status: LiveStatus = "idle"
    started_at: str | None = None
    finished_at: str | None = None
    report: dict[str, Any] | None = None
    error: str | None = None
    error_detail: str | None = None
    included_held_out: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "report": self.report,
            "error": self.error,
            "error_detail": self.error_detail,
            "included_held_out": self.included_held_out,
        }


_LIVE = LiveRunState()


def live_state() -> dict[str, Any]:
    with _LOCK:
        return _LIVE.as_dict()


def _run_live(include_held_out: bool) -> None:
    try:
        from docket.llm import get_chat_model

        report = serialize_report(
            run_eval(model=get_chat_model(), include_held_out=include_held_out)
        )
    except BaseException as exc:  # noqa: BLE001 - the message is the product here
        with _LOCK:
            _LIVE.status = "failed"
            _LIVE.finished_at = utc_now()
            _LIVE.error = f"{type(exc).__name__}: {exc}"
            _LIVE.error_detail = traceback.format_exc()
        return
    with _LOCK:
        _LIVE.status = "succeeded"
        _LIVE.finished_at = utc_now()
        _LIVE.report = report
        _LIVE.error = None
        _LIVE.error_detail = None


def start_live_run(*, include_held_out: bool = False) -> dict[str, Any]:
    """Start a live run on a background thread.

    `include_held_out` is the final run of docs/PROJECT.md 6.1. It raises
    `OverlayNotAuthored` inside the thread while any payload is still a
    placeholder -- reported as a failed run rather than silently skipped, so
    the dashboard can never show a held-out figure that was not measured.
    """
    with _LOCK:
        if _LIVE.status == "running":
            raise UiError("a live eval run is already in progress", status_code=409)
        _LIVE.status = "running"
        _LIVE.started_at = utc_now()
        _LIVE.finished_at = None
        _LIVE.report = None
        _LIVE.error = None
        _LIVE.error_detail = None
        _LIVE.included_held_out = include_held_out
    threading.Thread(
        target=_run_live, args=(include_held_out,), name="docket-live-eval", daemon=True
    ).start()
    return live_state()
