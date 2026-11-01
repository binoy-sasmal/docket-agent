"""The completion cap is part of a resume file's identity.

See tools/run_eval.py --max-completion-tokens.

Lowering the cap changes what the model may write, so results measured under
two caps describe two configurations and must never be merged into one number.
"""

from __future__ import annotations

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
