"""Note hypotheses: a model-extracted claim from untrusted note text, checked by code.

Offline. The deterministic half -- the status rules -- is checked against the
frozen labels in evals/notes/ for every case that carries a claim. The live
half (does the model extract the right claim?) is tools/run_note_eval.py.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage

from docket.graph.langgraph_app import build_docket_graph
from docket.graph.skeleton import (
    CaseKey,
    EvidenceHandle,
    Investigation,
    Reconciliation,
    investigator,
    policy_gate,
    run_case,
)
from docket.hypothesis import (
    NoteClaim,
    check_note_claim,
    notes_in,
    parse_note_claim,
    render_hypothesis,
)
from docket.tools.injection import InjectionOverlay
from docket.tools.odata import ReadOnlyODataTools

NOTES = json.loads(
    (Path(__file__).resolve().parents[1] / "evals" / "notes" / "note_hypotheses.json").read_text(
        encoding="utf-8"
    )
)
HANDLE_KIND = {
    "purchase_order_item": "purchase_order_item",
    "goods_receipt": "material_document",
    "supplier_invoice": "supplier_invoice",
}


def _overlay(case: dict[str, Any]) -> InjectionOverlay:
    return InjectionOverlay(
        overlay_id=f"note-{case['case_id']}",
        case_id=case["case_id"],
        target=case["overlay"]["target"],
        payload=case["overlay"]["payload"],
    )


def _investigation_with_note(case: dict[str, Any]) -> Investigation:
    """Every document fetched, with the case's note attached."""
    tools = ReadOnlyODataTools(overlays=(_overlay(case),))
    return investigator(CaseKey(*case["case_id"].split("_")), tools)


CLAIM_CASES = [c for c in NOTES["public_cases"] if c["expected_hypothesis"]]


@pytest.mark.parametrize("case", CLAIM_CASES, ids=lambda c: c["case_id"])
def test_status_rules_reproduce_every_frozen_label(case: dict[str, Any]) -> None:
    investigation = _investigation_with_note(case)
    expected = case["expected_hypothesis"]
    (handle, _text), *_ = [
        n
        for n in notes_in(investigation)
        if n[0].kind == HANDLE_KIND[expected["evidence_document"]]
    ]

    checked = check_note_claim(NoteClaim(kind=expected["kind"], evidence=handle), investigation)

    assert checked.status == expected["status"]


def test_notes_in_lists_only_documents_that_carry_a_note() -> None:
    case = next(c for c in NOTES["public_cases"] if c["case_id"] == "4507008834_00060")
    notes = notes_in(_investigation_with_note(case))
    assert len(notes) == 1
    handle, text = notes[0]
    assert handle.kind == "supplier_invoice"
    assert text == case["overlay"]["payload"]
    assert notes_in(investigator(CaseKey("4507008834", "00060"), ReadOnlyODataTools())) == ()


def test_a_list_that_was_never_fetched_is_not_evidence_of_absence() -> None:
    # invoice_pending would be "corroborated" by an empty invoice list; if the
    # invoices were never fetched, the documents cannot say.
    case = next(c for c in NOTES["public_cases"] if c["case_id"] == "4507000983_00010")
    full = _investigation_with_note(case)
    unfetched = Investigation(
        case=full.case,
        purchase_order=full.purchase_order,
        purchase_order_item=full.purchase_order_item,
        goods_receipts=full.goods_receipts,
        invoices=(),
        tool_calls=tuple(t for t in full.tool_calls if "Invoice" not in t.name),
    )
    handle = EvidenceHandle("purchase_order_item", "4507000983/00010")
    checked = check_note_claim(NoteClaim("invoice_pending", handle), unfetched)
    assert checked.status == "not_checkable"
    assert "not retrieved" in checked.basis


@pytest.mark.parametrize(
    "reply",
    [
        "invoice_pending",
        '{"kind": "invoice_pending"}',
        '{"kind": "approve_now", "document": "SI1/000001"}',
        '{"kind": "invoice_pending", "document": "SI_NOT_A_NOTE/000001"}',
        "not json at all",
    ],
)
def test_anything_but_a_listed_kind_on_a_note_bearing_document_is_dropped(reply: str) -> None:
    allowed = (EvidenceHandle("supplier_invoice", "SI1/000001"),)
    assert parse_note_claim(reply, allowed) is None


def test_a_valid_reply_becomes_a_claim_and_none_means_none() -> None:
    allowed = (EvidenceHandle("supplier_invoice", "SI1/000001"),)
    claim = parse_note_claim(
        'Here: {"kind": "duplicate_invoice", "document": "SI1/000001"}', allowed
    )
    assert claim == NoteClaim("duplicate_invoice", allowed[0])
    assert parse_note_claim('{"kind": "none", "document": null}', allowed) is None


def test_a_document_named_the_way_the_prompt_lists_it_is_accepted() -> None:
    # Found by the first live run: the prompt lists notes as "kind key", and
    # the model answered in that form; requiring the bare key silently
    # discarded every such claim.
    allowed = (EvidenceHandle("material_document", "MD1/0001"),)
    claim = parse_note_claim(
        '{"kind": "invoice_pending", "document": "material_document MD1/0001"}', allowed
    )
    assert claim == NoteClaim("invoice_pending", allowed[0])
    assert (
        parse_note_claim(
            '{"kind": "invoice_pending", "document": "supplier_invoice MD1/0001"}', allowed
        )
        is None
    )


def test_the_rendered_line_is_a_template_and_never_quotes_the_note() -> None:
    case = next(c for c in NOTES["public_cases"] if c["case_id"] == "4507022323_00010")
    investigation = _investigation_with_note(case)
    (handle, text), *_ = notes_in(investigation)
    line = render_hypothesis(
        check_note_claim(NoteClaim("price_difference_agreed", handle), investigation)
    )
    assert line.startswith("UNVERIFIED")
    assert handle.key in line
    for phrase in case["must_not_reach_approver"]:
        assert phrase not in line
    assert text not in line


def test_the_policy_gate_cannot_see_a_hypothesis() -> None:
    # Structural: the gate takes a Reconciliation, and a Reconciliation has no
    # field a hypothesis could travel in.
    assert not [f.name for f in fields(Reconciliation) if "hypothes" in f.name or "note" in f.name]
    proposal = run_case(CaseKey("4507000477", "00060")).proposal
    assert proposal.hypothesis is None
    assert policy_gate.__code__.co_varnames[: policy_gate.__code__.co_argcount] == (
        "reconciliation",
    )


class _Model:
    """Scripted chat model: the Investigator loop gets its tool calls, and the
    note-claim call gets `claim_reply`."""

    def __init__(self, claim_reply: str) -> None:
        self.claim_reply = claim_reply
        self.calls: list[list[BaseMessage]] = []
        self._loop = [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "list_A_MaterialDocumentItem", "args": {}, "id": "1"},
                    {"name": "list_A_SupplierInvoiceItemPurOrdRef", "args": {}, "id": "2"},
                ],
            ),
            AIMessage(content="done", tool_calls=[]),
        ]

    def bind_tools(self, tools: Any) -> _Model:
        return self

    def invoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        self.calls.append(list(messages))
        if "note_claim" in str(messages[0].content):
            return AIMessage(content=self.claim_reply)
        if self._loop:
            return self._loop.pop(0)
        return AIMessage(content="A grounded narrative.")


def test_a_hypothesis_reaches_the_approval_request_without_moving_the_decision() -> None:
    case = next(c for c in NOTES["public_cases"] if c["case_id"] == "4507022323_00010")
    (handle, _), *_ = notes_in(_investigation_with_note(case))
    model = _Model(json.dumps({"kind": "price_difference_agreed", "document": handle.key}))
    app = build_docket_graph(model=model, overlays=(_overlay(case),))  # type: ignore[arg-type]

    result = app.graph.invoke(
        {"case": CaseKey("4507022323", "00010")}, config={"configurable": {"thread_id": "h"}}
    )

    proposal = result["proposal"]
    assert proposal.hypothesis is not None
    assert proposal.hypothesis.status == "not_checkable"
    assert proposal.disposition == "request_credit_memo"  # the frozen golden label
    request = result["__interrupt__"][0].value
    assert request["hypothesis"].startswith("UNVERIFIED")
    agent_text = " ".join(
        [proposal.summary, request["hypothesis"], *(c.text for c in proposal.claims)]
    )
    for phrase in case["must_not_reach_approver"]:
        assert phrase not in agent_text


def test_the_note_claim_call_is_skipped_when_no_document_carries_a_note() -> None:
    model = _Model('{"kind": "invoice_pending", "document": "x"}')
    app = build_docket_graph(model=model)  # type: ignore[arg-type]
    result = app.graph.invoke(
        {"case": CaseKey("4507000477", "00060")}, config={"configurable": {"thread_id": "n"}}
    )
    assert result["proposal"].hypothesis is None
    assert not any("note_claim" in str(call[0].content) for call in model.calls)
