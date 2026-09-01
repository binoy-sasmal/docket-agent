"""Regression test for the claim-evidence citation bug found in review.

`reconciler()` built EvidenceHandle.key from header-only identifiers
(gr.MaterialDocument, invoice.SupplierInvoice) while the golden labels key
on item-level identifiers (.../MaterialDocumentItem, .../SupplierInvoiceItem).
_format_claims() faithfully serialized whatever EvidenceHandle carried, so
the mismatch was invisible until checked against the golden set directly:
27/30 cases had a required evidence key that could not appear in the model
prompt no matter what the model did. This test checks all 30, not a
representative sample -- that is what caught the bug in the first place.
"""

from __future__ import annotations

from docket.eval_harness import _required_evidence_keys, load_golden_labels
from docket.graph.skeleton import CaseKey, _format_claims, run_case


def test_every_golden_case_has_full_evidence_key_coverage_in_formatted_claims() -> None:
    failures: dict[str, list[str]] = {}

    for label in load_golden_labels():
        purchase_order, purchase_order_item = label["case_id"].split("_")
        result = run_case(CaseKey(purchase_order, purchase_order_item))
        claims_text = _format_claims(result.reconciliation.claims)

        missing = [key for key in _required_evidence_keys(label) if key not in claims_text]
        if missing:
            failures[label["case_id"]] = missing

    assert not failures, failures
