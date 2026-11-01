"""The completion cap is part of a resume file's identity.

See tools/run_eval.py --max-completion-tokens.

Lowering the cap changes what the model may write, so results measured under
two caps describe two configurations and must never be merged into one number.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from docket.eval_harness import ResumeConflict, agent_fingerprint, run_agent_id, run_eval
from docket.llm import MAX_COMPLETION_TOKENS


def test_default_cap_keeps_the_plain_fingerprint() -> None:
    assert run_agent_id() == agent_fingerprint()
    assert run_agent_id(MAX_COMPLETION_TOKENS) == agent_fingerprint()


def test_a_lower_cap_changes_the_identity() -> None:
    assert run_agent_id(1300) == f"{agent_fingerprint()}+max_completion_tokens=1300"


def test_results_from_two_caps_are_never_merged(tmp_path) -> None:
    resume = tmp_path / "run.json"
    run_eval(resume_path=resume)  # deterministic, default cap
    with pytest.raises(ResumeConflict, match="agent fingerprint"):
        run_eval(resume_path=resume, max_completion_tokens=1300)


def test_the_same_cap_resumes_cleanly(tmp_path) -> None:
    resume = tmp_path / "run.json"
    run_eval(resume_path=resume, max_completion_tokens=1300)
    report = run_eval(resume_path=resume, max_completion_tokens=1300)
    assert report.reused_case_runs == len(report.results)


@pytest.mark.parametrize("cap", [0, -1])
def test_a_non_positive_cap_is_rejected_not_recorded(cap: int, tmp_path) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        run_agent_id(cap)
    resume = tmp_path / "run.json"
    with pytest.raises(ValueError, match="positive integer"):
        run_eval(resume_path=resume, max_completion_tokens=cap)
    assert not resume.exists()


@pytest.mark.parametrize("cap", ["0", "-1", "abc"])
def test_the_cli_rejects_a_non_positive_cap(cap: str) -> None:
    # argparse fails before any model is built or file opened, so this needs no API key.
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    done = subprocess.run(
        [sys.executable, str(root / "tools" / "run_eval.py"), "--max-completion-tokens", cap],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert done.returncode == 2
    assert "must be a positive integer" in done.stderr
