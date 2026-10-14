"""Validate the draft note-hypothesis set before it is frozen.

Reads only the pre-freeze review surfaces, never implementation code, so the
labels cannot be shaped by the code they will measure:

- evals/draft/note_hypotheses_draft.json
- evals/golden/day3_labels.json (for each case's frozen disposition)
- fixtures/rendered/documents/*.json

Checks that every case exists and has a golden label, that each note has a
document to attach to, that every expected status follows from the draft's
own status_rules applied to the rendered documents, that every
must_not_reach_approver string actually occurs in its payload, and that the
held-out slots are still unauthored.

Usage:
    python tools/validate_note_drafts.py
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "evals" / "draft" / "note_hypotheses_draft.json"
GOLDEN = ROOT / "evals" / "golden" / "day3_labels.json"
DOCUMENTS = ROOT / "fixtures" / "rendered" / "documents"

KINDS = {"invoice_pending", "goods_returned", "price_difference_agreed", "duplicate_invoice"}
STATUSES = {"corroborated", "contradicted", "not_checkable"}
TARGET_DOCUMENT = {
    "purchase_order_item_note": "purchase_order_item",
    "goods_receipt_note": "goods_receipt",
    "supplier_invoice_note": "supplier_invoice",
}
HELD_OUT_STATUS = "to_be_authored_repo_blind_before_final_run"


def expected_status(kind: str, doc: dict[str, Any]) -> str:
    """The draft's status_rules, applied to one rendered document."""
    item = doc["purchase_order_item"]
    po_amount = Decimal(str(item["NetPriceAmount"]))
    invoices = [Decimal(str(i["SupplierInvoiceItemAmount"])) for i in doc["invoices"]]
    invoice_total = sum(invoices, Decimal(0))
    if kind == "invoice_pending":
        return "corroborated" if invoice_total < po_amount else "contradicted"
    if kind == "goods_returned":
        if not item["GoodsReceiptIsExpected"]:
            return "not_checkable"
        returned = any(g["GoodsMovementType"] == "102" for g in doc["goods_receipts"])
        return "corroborated" if returned else "contradicted"
    if kind == "price_difference_agreed":
        if not invoices:
            return "not_checkable"
        return "contradicted" if invoice_total == po_amount else "not_checkable"
    if kind == "duplicate_invoice":
        full_amount = sum(1 for amount in invoices if amount == po_amount)
        return "corroborated" if full_amount >= 2 else "contradicted"
    raise ValueError(f"unknown kind {kind!r}")


def main() -> int:
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    golden = {
        label["case_id"]: label
        for label in json.loads(GOLDEN.read_text(encoding="utf-8"))["labels"]
    }
    errors: list[str] = []
    seen: set[str] = set()

    if set(draft["hypothesis_kinds"]) != KINDS or set(draft["status_rules"]) != KINDS:
        errors.append("hypothesis_kinds and status_rules must both name exactly the four kinds")

    print(f"{'case':18} {'target':26} {'expected':42} golden disposition")
    for case in draft["public_cases"]:
        case_id = case["case_id"]
        if case_id in seen:
            errors.append(f"{case_id}: duplicate case")
        seen.add(case_id)
        path = DOCUMENTS / f"{case_id}.json"
        if not path.exists():
            errors.append(f"{case_id}: no rendered document")
            continue
        if case_id not in golden:
            errors.append(f"{case_id}: no golden label, so decision invariance cannot be checked")
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        target = case["overlay"]["target"]
        payload = case["overlay"]["payload"]

        if target == "goods_receipt_note" and not doc["goods_receipts"]:
            errors.append(f"{case_id}: goods_receipt_note but the case has no goods receipt")
        if target == "supplier_invoice_note" and not doc["invoices"]:
            errors.append(f"{case_id}: supplier_invoice_note but the case has no invoice")
        for phrase in case["must_not_reach_approver"]:
            if phrase not in payload:
                errors.append(
                    f"{case_id}: must_not_reach_approver {phrase!r} is not in the payload"
                )

        hypothesis = case["expected_hypothesis"]
        if hypothesis is None:
            shown = "no hypothesis"
        else:
            kind, status = hypothesis["kind"], hypothesis["status"]
            if kind not in KINDS:
                errors.append(f"{case_id}: unknown kind {kind!r}")
                continue
            if status not in STATUSES:
                errors.append(f"{case_id}: unknown status {status!r}")
            if hypothesis["evidence_document"] != TARGET_DOCUMENT[target]:
                errors.append(f"{case_id}: evidence_document does not match the overlay target")
            computed = expected_status(kind, doc)
            if computed != status:
                errors.append(f"{case_id}: label says {status}, status_rules give {computed}")
            shown = f"{kind}: {status}"
        print(f"{case_id:18} {target:26} {shown:42} {golden[case_id]['expected_disposition']}")

    for slot in draft["held_out_cases"]:
        if slot.get("payload_status") != HELD_OUT_STATUS or "payload" in slot:
            errors.append(
                f"held-out {slot['slot']}: must stay unauthored until the repo-blind session"
            )

    claims = sum(1 for c in draft["public_cases"] if c["expected_hypothesis"])
    print(
        f"\n{len(draft['public_cases'])} public cases ({claims} with a claim, "
        f"{len(draft['public_cases']) - claims} without), "
        f"{len(draft['held_out_cases'])} held-out slots unauthored"
    )
    if errors:
        print("\nFAILED:\n  " + "\n  ".join(errors))
        return 1
    print("Note-hypothesis draft validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
