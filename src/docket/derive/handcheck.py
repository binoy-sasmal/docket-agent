"""Generate the three hand-check reports required by docs/PROJECT.md section
7 (Day 1, gate 1) -- "three cases are hand-checked against the raw event
rows by a human. Do not skip the hand-check; this is the step most likely to
be quietly wrong."

Each report shows, for one case: every raw event row in full, in timestamp
order, next to the rendered document, with the arithmetic shown -- every
attribution and every assumption applied, named. The human reviewer signs
off by committing docs/handcheck/VERIFIED.md; that signature, not this
script's output, is the actual gate. This script only makes the check
possible to perform quickly and completely.

HANDCHECK_CASES below is chosen to cover the risky reconstruction paths, not
the easy ones (docs/DERIVATION.md and the Session 1 plan, section B8):

1. A clean single-GR, single-invoice 3-way case -- the baseline.
2. A multi-GR case -- the shape most likely to be wrong. Chosen here is
   4508063534_00001, the smaller of the two ">20" bucket cases in the
   selection (102 goods receipts), which stress-tests the amount-split and
   reversal-matching logic hardest.
3. A 2-way-match case -- the shape where the GR logic must not fire at all.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from docket.derive.load import load_raw
from docket.derive.render import render_case
from docket.schema.procurement import RenderedLineItem

HANDCHECK_CASES: dict[str, str] = {
    "4507000477_00060": "clean single-GR / single-invoice, 3-way (invoice before GR)",
    "4508063534_00001": "multi-GR (102 goods receipts), 3-way (invoice after GR)",
    "4507075965_00050": "2-way match -- GR logic must not fire",
}

HANDCHECK_NOTES: dict[str, str] = {
    "4508063534_00001": (
        "**Reviewer note:** this case's raw `Cumulative net worth (EUR)` "
        "column is NOT constant -- individual `Record Goods Receipt` rows "
        "show wildly different values (131.0, 384.0, ...) than the case's "
        "`Create Purchase Order Item` / `Record Service Entry Sheet` rows "
        "(a consistent 9.0). This was caught by this hand-check and is "
        "documented in docs/DERIVATION.md section 1.10.1 -- the renderer "
        "deliberately does not trust the per-GR values (hence the 'authored' "
        "provenance on the split below) and derives the case total from the "
        "first event instead, which for every eligible case is always the "
        "creation event. Please check that this reasoning holds up."
    ),
}

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "docs" / "handcheck"

RAW_COLUMNS = [
    "eventID ",
    "event concept:name",
    "event User",
    "event Cumulative net worth (EUR)",
    "event time:timestamp",
]


def _raw_trace_table(trace: pd.DataFrame) -> str:
    ordered = trace.sort_values(["event time:timestamp", "eventID "])
    lines = ["| eventID | Activity | User | Cumulative net worth (EUR) | Timestamp |"]
    lines.append("|---|---|---|---|---|")
    for _, row in ordered.iterrows():
        lines.append(
            f"| {row['eventID ']} "
            f"| {row['event concept:name']} "
            f"| {row['event User']} "
            f"| {row['event Cumulative net worth (EUR)']} "
            f"| {row['event time:timestamp']} |"
        )
    return "\n".join(lines)


def _rendered_summary(doc: RenderedLineItem) -> str:
    lines = [
        f"- **PurchaseOrder / Item:** {doc.purchase_order_item.PurchaseOrder} / "
        f"{doc.purchase_order_item.PurchaseOrderItem}",
        f"- **Category:** {doc.purchase_order_item.PurchaseOrderItemCategory}",
        f"- **GoodsReceiptIsExpected:** {doc.purchase_order_item.GoodsReceiptIsExpected}"
        f"  **InvoiceIsGoodsReceiptBased:** {doc.purchase_order_item.InvoiceIsGoodsReceiptBased}",
        f"- **NetPriceAmount (log-derived, from 'Cumulative net worth (EUR)' at the "
        f"case's first event):** {doc.purchase_order_item.NetPriceAmount}",
        "",
        f"**Goods receipts rendered: {len(doc.goods_receipts)}**",
    ]
    for gr in doc.goods_receipts:
        reversal_note = (
            f" (reverses {gr.ReversesMaterialDocument})" if gr.ReversesMaterialDocument else ""
        )
        lines.append(
            f"  - {gr.MaterialDocument} type={gr.GoodsMovementType} "
            f"amount={gr.Amount} provenance={gr.AmountProvenance.value}{reversal_note}"
        )
    gr_sum = sum(g.Amount for g in doc.goods_receipts if g.GoodsMovementType == "101")
    lines.append(f"  - **sum of 101 (non-reversal) amounts: {gr_sum}**")

    lines.append("")
    lines.append(f"**Invoices rendered: {len(doc.invoices)}**")
    for iv in doc.invoices:
        ref_note = (
            f" references={iv.ReferencesMaterialDocument}" if iv.ReferencesMaterialDocument else ""
        )
        rev_note = f" (reverses {iv.ReverseDocument})" if iv.ReverseDocument else ""
        lines.append(
            f"  - {iv.SupplierInvoice} amount={iv.SupplierInvoiceItemAmount} "
            f"provenance={iv.AmountProvenance.value}{ref_note}{rev_note}"
        )
    iv_sum = sum(i.SupplierInvoiceItemAmount for i in doc.invoices if i.ReverseDocument is None)
    lines.append(f"  - **sum of non-reversal amounts: {iv_sum}**")

    total = doc.purchase_order_item.NetPriceAmount
    n_gr_original = sum(1 for g in doc.goods_receipts if g.GoodsMovementType == "101")
    n_iv_original = sum(1 for i in doc.invoices if i.ReverseDocument is None)
    if n_gr_original == 0:
        gr_check = "N/A -- no goods receipts rendered (correct if GoodsReceiptIsExpected=False)"
    else:
        gr_check = f"{gr_sum == total} ({gr_sum} vs {total})"
    if n_iv_original == 0:
        iv_check = "N/A -- no invoices rendered"
    else:
        iv_check = f"{iv_sum == total} ({iv_sum} vs {total})"
    lines.append("")
    lines.append(
        f"**Conservation check:** GR sum == NetPriceAmount: {gr_check}. "
        f"Invoice sum == NetPriceAmount: {iv_check}."
    )
    return "\n".join(lines)


def generate_report(case_id: str, description: str, df: pd.DataFrame) -> str:
    trace = df[df["case concept:name"] == case_id]
    if trace.empty:
        raise ValueError(f"case_id {case_id!r} not found in the loaded frame")
    doc = render_case(trace)
    note = HANDCHECK_NOTES.get(case_id, "")
    note_block = f"\n{note}\n" if note else ""

    return f"""# Hand-check: {case_id}

**Why this case was chosen:** {description}
{note_block}
## 1. Raw event rows (source of truth)

{_raw_trace_table(trace)}

## 2. Rendered document

{_rendered_summary(doc)}

## 3. Assumptions applied

- Case total order value taken from `Cumulative net worth (EUR)` at the
  case's earliest event (docs/DERIVATION.md 1.10) -- log-derived.
- Where more than one goods receipt or invoice exists, the total above is
  split evenly across them (authored -- docs/DERIVATION.md 1.10). Where
  exactly one of each exists, both take the total directly (log-derived).
- `Cancel Goods Receipt` / `Cancel Invoice Receipt` events are matched LIFO
  to the most recent not-yet-reversed original of the same type, and copy
  its amount (authored inference -- the log carries no reference field for
  this).
- Positional GR/invoice matching (docs/DERIVATION.md 3.2) applies only to
  "3-way match, invoice after GR" items: the k-th invoice references the
  k-th goods receipt in time order.

## 4. Reviewer sign-off

Reviewed by: _______________  Date: _______________

Checked against the raw rows above and found: _______________________________
"""


def main() -> None:
    df = load_raw()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for case_id, description in HANDCHECK_CASES.items():
        report = generate_report(case_id, description, df)
        path = OUTPUT_DIR / f"{case_id}.md"
        path.write_text(report, encoding="utf-8", newline="\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
