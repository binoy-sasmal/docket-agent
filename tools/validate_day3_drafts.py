"""Validate draft Day 3 labels before freezing.

This script intentionally reads only the pre-freeze review surfaces:

- evals/draft/day3_labels_draft.json
- evals/draft/injection_overlays_draft.json
- fixtures/frozen/selection/cases.json
- fixtures/rendered/documents/*.json

It does not import implementation modules or inspect tests.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

EXPECTED_DISPOSITIONS = {"post", "hold", "request_credit_memo", "escalate", "route"}
EXPECTED_REASON_CODES = {
    "matched_3way",
    "matched_2way",
    "no_invoice",
    "over_invoiced",
    "over_receipted_no_invoice",
    "consignment",
}
REQUIRED_EVIDENCE_FIELDS = {
    "purchase_order_item",
    "goods_receipts",
    "supplier_invoice_items",
}
HELD_OUT_PAYLOAD_STATUS = "to_be_authored_repo_blind_before_final_run"


@dataclass(frozen=True)
class Totals:
    category: str
    po_amount: Decimal
    gr_count: int
    gr_total: Decimal
    invoice_count: int
    invoice_total: Decimal


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def amount(value: str | int | float | None) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def rendered_path(repo_root: Path, case_id: str) -> Path:
    return repo_root / "fixtures" / "rendered" / "documents" / f"{case_id}.json"


def po_key(document: dict[str, Any]) -> str:
    item = document["purchase_order_item"]
    return f"{item['PurchaseOrder']}/{item['PurchaseOrderItem']}"


def gr_keys(document: dict[str, Any]) -> set[str]:
    return {
        f"{receipt['MaterialDocument']}/{receipt['MaterialDocumentItem']}"
        for receipt in document["goods_receipts"]
    }


def invoice_keys(document: dict[str, Any]) -> set[str]:
    return {
        f"{invoice['SupplierInvoice']}/{invoice['SupplierInvoiceItem']}"
        for invoice in document["invoices"]
    }


def totals(document: dict[str, Any]) -> Totals:
    item = document["purchase_order_item"]
    return Totals(
        category=item["PurchaseOrderItemCategory"],
        po_amount=amount(item["NetPriceAmount"]),
        gr_count=len(document["goods_receipts"]),
        gr_total=sum(
            (amount(receipt["Amount"]) for receipt in document["goods_receipts"]),
            Decimal("0"),
        ),
        invoice_count=len(document["invoices"]),
        invoice_total=sum(
            (amount(invoice["SupplierInvoiceItemAmount"]) for invoice in document["invoices"]),
            Decimal("0"),
        ),
    )


def validate_schema(labels: dict[str, Any], errors: list[str]) -> None:
    schema = labels.get("disposition_schema")
    if not isinstance(schema, dict):
        errors.append("labels: missing disposition_schema object")
        return

    dispositions = set(schema.get("expected_disposition", []))
    reason_codes = set(schema.get("reason_code", []))
    if dispositions != EXPECTED_DISPOSITIONS:
        errors.append(
            "labels: disposition_schema expected_disposition mismatch: "
            f"{sorted(dispositions)}"
        )
    if reason_codes != EXPECTED_REASON_CODES:
        errors.append(f"labels: disposition_schema reason_code mismatch: {sorted(reason_codes)}")


def validate_evidence(
    label: dict[str, Any],
    document: dict[str, Any],
    errors: list[str],
) -> None:
    case_id = label["case_id"]
    evidence = label.get("evidence_keys")
    required = label.get("required_evidence_sets")

    if not isinstance(evidence, dict):
        errors.append(f"{case_id}: missing evidence_keys object")
        return
    if not isinstance(required, dict):
        errors.append(f"{case_id}: missing required_evidence_sets object")
        return

    if set(evidence) != REQUIRED_EVIDENCE_FIELDS:
        errors.append(f"{case_id}: evidence_keys must contain {sorted(REQUIRED_EVIDENCE_FIELDS)}")
    if evidence != required:
        errors.append(f"{case_id}: required_evidence_sets must match evidence_keys")

    if evidence.get("purchase_order_item") != po_key(document):
        errors.append(
            f"{case_id}: purchase_order_item evidence {evidence.get('purchase_order_item')} "
            f"does not match rendered {po_key(document)}"
        )

    rendered_gr_keys = gr_keys(document)
    evidence_gr_keys = set(evidence.get("goods_receipts", []))
    if evidence_gr_keys != rendered_gr_keys:
        missing = sorted(rendered_gr_keys - evidence_gr_keys)
        extra = sorted(evidence_gr_keys - rendered_gr_keys)
        errors.append(
            f"{case_id}: goods receipt evidence keys must exactly match rendered keys; "
            f"missing {missing}, extra {extra}"
        )

    rendered_invoice_keys = invoice_keys(document)
    evidence_invoice_keys = set(evidence.get("supplier_invoice_items", []))
    if evidence_invoice_keys != rendered_invoice_keys:
        missing = sorted(rendered_invoice_keys - evidence_invoice_keys)
        extra = sorted(evidence_invoice_keys - rendered_invoice_keys)
        errors.append(
            f"{case_id}: supplier invoice evidence keys must exactly match rendered keys; "
            f"missing {missing}, extra {extra}"
        )


def validate_gr_based_references(
    case_id: str,
    document: dict[str, Any],
    errors: list[str],
) -> None:
    receipt_doc_counts = Counter(
        receipt["MaterialDocument"] for receipt in document["goods_receipts"]
    )
    duplicate_receipt_docs = sorted(
        material_document
        for material_document, count in receipt_doc_counts.items()
        if count > 1
    )
    if duplicate_receipt_docs:
        errors.append(
            f"{case_id}: GR-based post has multiple receipt items for material documents "
            f"{duplicate_receipt_docs}; reference validation is ambiguous"
        )
        return

    receipt_amount_by_doc = {
        receipt["MaterialDocument"]: amount(receipt["Amount"])
        for receipt in document["goods_receipts"]
    }
    invoice_amount_by_ref: dict[str, Decimal] = {}

    for invoice in document["invoices"]:
        reference = invoice.get("ReferencesMaterialDocument")
        if not reference:
            errors.append(f"{case_id}: GR-based post invoice has no material document reference")
            continue
        invoice_amount_by_ref[reference] = (
            invoice_amount_by_ref.get(reference, Decimal("0"))
            + amount(invoice["SupplierInvoiceItemAmount"])
        )

    if set(receipt_amount_by_doc) != set(invoice_amount_by_ref):
        errors.append(
            f"{case_id}: GR-based post references do not cover exactly the rendered GR documents"
        )
        return

    for material_document, receipt_amount in receipt_amount_by_doc.items():
        invoice_amount = invoice_amount_by_ref[material_document]
        if receipt_amount != invoice_amount:
            errors.append(
                f"{case_id}: referenced amount mismatch for {material_document}: "
                f"GR {receipt_amount} vs invoice {invoice_amount}"
            )


def validate_disposition(
    label: dict[str, Any],
    document: dict[str, Any],
    errors: list[str],
) -> None:
    case_id = label["case_id"]
    disposition = label.get("expected_disposition")
    reason_code = label.get("reason_code")
    computed = totals(document)

    if disposition not in EXPECTED_DISPOSITIONS:
        errors.append(f"{case_id}: invalid expected_disposition {disposition!r}")
    if reason_code not in EXPECTED_REASON_CODES:
        errors.append(f"{case_id}: invalid reason_code {reason_code!r}")

    if disposition == "post" and reason_code == "matched_3way":
        if "3-way match" not in computed.category:
            errors.append(
                f"{case_id}: matched_3way post on non-3-way category "
                f"{computed.category!r}"
            )
        if computed.po_amount != computed.gr_total or computed.po_amount != computed.invoice_total:
            errors.append(
                f"{case_id}: matched_3way post totals mismatch: "
                f"PO {computed.po_amount}, GR {computed.gr_total}, invoice {computed.invoice_total}"
            )
        if computed.category == "3-way match, invoice after GR":
            validate_gr_based_references(case_id, document, errors)

    elif disposition == "post" and reason_code == "matched_2way":
        if computed.category != "2-way match":
            errors.append(f"{case_id}: matched_2way post on category {computed.category!r}")
        if computed.gr_count != 0:
            errors.append(f"{case_id}: matched_2way post should not have GRs")
        if computed.po_amount != computed.invoice_total:
            errors.append(
                f"{case_id}: matched_2way post totals mismatch: "
                f"PO {computed.po_amount}, invoice {computed.invoice_total}"
            )

    elif disposition == "request_credit_memo" and reason_code == "over_invoiced":
        if (
            computed.invoice_total <= computed.po_amount
            or computed.invoice_total <= computed.gr_total
        ):
            errors.append(
                f"{case_id}: over_invoiced should exceed PO and GR: "
                f"PO {computed.po_amount}, GR {computed.gr_total}, invoice {computed.invoice_total}"
            )

    elif disposition == "hold" and reason_code == "no_invoice":
        if computed.invoice_count != 0:
            errors.append(
                f"{case_id}: no_invoice hold has "
                f"{computed.invoice_count} rendered invoices"
            )

    elif disposition == "escalate" and reason_code == "over_receipted_no_invoice":
        if computed.invoice_count != 0:
            errors.append(f"{case_id}: over_receipted_no_invoice has rendered invoices")
        if computed.gr_total <= computed.po_amount:
            errors.append(
                f"{case_id}: over_receipted_no_invoice should have GR total > PO: "
                f"PO {computed.po_amount}, GR {computed.gr_total}"
            )

    elif disposition == "route" and reason_code == "consignment":
        if computed.category != "Consignment":
            errors.append(f"{case_id}: consignment route on category {computed.category!r}")

    else:
        errors.append(f"{case_id}: unsupported disposition/reason pair {disposition}/{reason_code}")


def validate_overlays(
    labels: list[dict[str, Any]],
    overlays: dict[str, Any],
    errors: list[str],
) -> None:
    public = overlays.get("public_overlays", [])
    held_out = overlays.get("held_out_overlays", [])
    if len(public) != 4:
        errors.append(f"overlays: expected 4 public overlays, found {len(public)}")
    if len(held_out) != 4:
        errors.append(f"overlays: expected 4 held-out overlays, found {len(held_out)}")

    injection_labels = {
        label["injection_overlay_id"]: label["case_id"]
        for label in labels
        if label.get("is_injection_case")
    }
    overlay_ids = [overlay["overlay_id"] for overlay in [*public, *held_out]]
    for overlay_id, count in Counter(overlay_ids).items():
        if count != 1:
            errors.append(f"overlays: duplicate overlay_id {overlay_id}")

    for overlay in public:
        overlay_id = overlay.get("overlay_id")
        if "payload" not in overlay:
            errors.append(f"{overlay_id}: public overlay must include payload")
        if injection_labels.get(overlay_id) != overlay.get("case_id"):
            errors.append(f"{overlay_id}: public overlay does not match an injection label")

    for overlay in held_out:
        overlay_id = overlay.get("overlay_id")
        if "payload" in overlay:
            errors.append(f"{overlay_id}: held-out overlay must not contain payload text")
        if overlay.get("payload_status") != HELD_OUT_PAYLOAD_STATUS:
            errors.append(f"{overlay_id}: invalid held-out payload_status")
        if injection_labels.get(overlay_id) != overlay.get("case_id"):
            errors.append(f"{overlay_id}: held-out overlay does not match an injection label")

    for overlay_id in injection_labels:
        if overlay_id not in overlay_ids:
            errors.append(f"{overlay_id}: injection label has no overlay")


def validate(repo_root: Path) -> list[str]:
    labels_path = repo_root / "evals" / "draft" / "day3_labels_draft.json"
    overlays_path = repo_root / "evals" / "draft" / "injection_overlays_draft.json"
    selection_path = repo_root / "fixtures" / "frozen" / "selection" / "cases.json"

    labels_document = load_json(labels_path)
    overlays_document = load_json(overlays_path)
    selection_document = load_json(selection_path)

    labels = labels_document.get("labels", [])
    selected_case_ids = set(selection_document.get("selected_case_ids", []))
    errors: list[str] = []

    validate_schema(labels_document, errors)

    case_counts = Counter(label.get("case_id") for label in labels)
    for case_id, count in case_counts.items():
        if count != 1:
            errors.append(f"{case_id}: duplicate label count {count}")

    for label in labels:
        case_id = label.get("case_id")
        if not case_id:
            errors.append("label missing case_id")
            continue
        if case_id not in selected_case_ids:
            errors.append(f"{case_id}: not present in fixtures/frozen/selection/cases.json")

        path = rendered_path(repo_root, case_id)
        if not path.exists():
            errors.append(f"{case_id}: rendered document missing at {path}")
            continue

        rendered_document = load_json(path)
        validate_evidence(label, rendered_document, errors)
        validate_disposition(label, rendered_document, errors)

    validate_overlays(labels, overlays_document, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the parent of tools/.",
    )
    args = parser.parse_args()

    errors = validate(args.repo_root.resolve())
    if errors:
        print(f"Day 3 draft validation failed with {len(errors)} issue(s):")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Day 3 draft validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
