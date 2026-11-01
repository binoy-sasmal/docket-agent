"""Prompt layouts for the Reconciler and Proposer calls (DOCKET_PROMPT_LAYOUT).

`shared_prefix` exists so provider prompt caching can reuse the Reconciler
call's prefix on the Proposer call. These tests pin the two properties that
matter: the prefix really is identical, and moving the task instructions to
the end dropped nothing the old prompts carried.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage

from docket.eval_harness import agent_fingerprint
from docket.graph import skeleton
from docket.graph.skeleton import (
    CaseKey,
    proposer_justification,
    reconciler_narrative,
    run_case,
)

THREE_WAY_CASE = CaseKey("4507000477", "00060")


class _Recorder:
    def __init__(self) -> None:
        self.invocations: list[list[BaseMessage]] = []

    def invoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        self.invocations.append(list(messages))
        return AIMessage(content="ok")


def _both_calls() -> tuple[list[BaseMessage], list[BaseMessage], object]:
    run = run_case(THREE_WAY_CASE)
    model = _Recorder()
    reconciler_narrative(run.reconciliation, model)  # type: ignore[arg-type]
    proposer_justification(run.reconciliation, run.policy, model)  # type: ignore[arg-type]
    return model.invocations[0], model.invocations[1], run


def test_default_layout_keeps_the_measured_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCKET_PROMPT_LAYOUT", raising=False)
    reconciler_call, proposer_call, _ = _both_calls()
    assert reconciler_call[0] == SystemMessage(skeleton._RECONCILER_SYSTEM_PROMPT)
    assert proposer_call[0] == SystemMessage(skeleton._PROPOSER_SYSTEM_PROMPT)
    assert len(reconciler_call) == len(proposer_call) == 2


def test_shared_prefix_gives_both_calls_an_identical_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOCKET_PROMPT_LAYOUT", "shared_prefix")
    reconciler_call, proposer_call, run = _both_calls()

    assert [m.content for m in reconciler_call[:2]] == [m.content for m in proposer_call[:2]]
    assert reconciler_call[2].content != proposer_call[2].content
    # Every claim is in the shared prefix; only task text follows it.
    claims_message = str(reconciler_call[1].content)
    assert all(claim.text in claims_message for claim in run.reconciliation.claims)


def test_shared_prefix_proposer_task_keeps_every_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCKET_PROMPT_LAYOUT", "shared_prefix")
    _, proposer_call, run = _both_calls()
    task = str(proposer_call[-1].content)
    assert run.policy.reason in task
    for rule in (
        "literally include every evidence key",
        "do not paraphrase or drop any of them",
        "Do not invent evidence",
        "do not claim anything was approved already",
        "a human must approve it",
    ):
        assert rule in task


def test_layouts_never_share_a_fingerprint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCKET_PROMPT_LAYOUT", raising=False)
    default = agent_fingerprint()
    monkeypatch.setenv("DOCKET_PROMPT_LAYOUT", "default")
    assert agent_fingerprint() == default
    monkeypatch.setenv("DOCKET_PROMPT_LAYOUT", "shared_prefix")
    assert agent_fingerprint() != default


def test_an_unknown_layout_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCKET_PROMPT_LAYOUT", "shared-prefix")
    with pytest.raises(ValueError, match="DOCKET_PROMPT_LAYOUT"):
        skeleton.prompt_layout()
