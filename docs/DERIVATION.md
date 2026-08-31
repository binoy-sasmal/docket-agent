# BPIC 2019 derivation — reconnaissance, decisions, schema, provenance

This document is the Session 1 record required by `docs/PROJECT.md` §6.1 and
§7: what was found in the raw log, what was decided as a result, and why.
It folds together the reconnaissance findings, the schema reference, and the
field-group provenance tagging into one place.

Source files and licence: see `data/raw/SOURCES.md`.

---

## 1. Reconnaissance

Run against the full CSV (`src/docket/derive/load.py::load_raw`), 2026-08-31.
Timeboxed to 90 minutes per the Session 1 plan; the required items (1-10)
plus the opportunistic amounts glance (11) were all completed in well under
that budget.

### 1.1 File identity (plan B1 / B3 items 1-2)

Header matched `EXPECTED_COLUMNS` exactly (`load.py` asserts this and raises
if not). Row counts match `docs/PROJECT.md` §4.1 exactly:

| Metric | Found | §4.1 |
|---|---|---|
| Purchase documents | 76,349 | 76,349 |
| Cases (line items) | 251,734 | 251,734 |
| Events | 1,595,923 | 1,595,923 |
| Activities | 42 | 42 |

Combined with the XES/MD5 cross-check in `SOURCES.md`, file identity is
confirmed by two independent methods.

**Encoding note (not anticipated in the plan):** the CSV is not UTF-8 — byte
`0x96` (a Windows-1252 en-dash) appears at least once. `load.py` reads with
`encoding="cp1252"`.

### 1.2 Item Category distribution (plan B3 item 3)

**This overturns an assumption in the Session 1 plan.** Secondary EDA
sources suggested "3-way match, invoice after GR" was the dominant category;
the actual per-case distribution is the reverse:

| Item Category | Cases | Share |
|---|---|---|
| 3-way match, invoice before GR | 221,010 | 87.8% |
| 3-way match, invoice after GR | 15,182 | 6.0% |
| Consignment | 14,498 | 5.8% |
| 2-way match | 1,044 | 0.4% |

This does not change the planned allocation (110/110/50/30) — every stratum
has far more raw cases available than its allocation requires, so there is
no stratum-availability shortfall at the category level. It does mean the
"before GR" stratum is drawing from a much larger and more typical
population than "after GR", worth noting if the two 3-way strata turn out to
look different in character.

### 1.3 Activity vocabulary (plan B3 item 4)

All 42 activities present; full frequency table available by re-running
`src/docket/derive/profile.py`. Notable: `Record Goods Receipt` (314,097
events) exceeds the case count (251,734), confirming multi-GR is common from
the very first cut. `Record Service Entry Sheet` (164,975) is a
service-item-specific activity, relevant to `Item Type = Service` cases.

### 1.4 GR/IR count distribution per case, per category (plan B3 item 5)

GR-count bucketed as `{0, 1, 2-5, 6-20, >20}`:

| Category | 0 | 1 | 2-5 | 6-20 | >20 |
|---|---|---|---|---|---|
| 2-way match | 1,044 | 0 | 0 | 0 | 0 |
| 3-way, invoice after GR | 643 | 10,294 | 2,162 | 1,322 | 761 |
| 3-way, invoice before GR | 14,536 | 199,385 | 6,581 | 386 | 122 |
| Consignment | 1,032 | 12,122 | 1,307 | 37 | 0 |

2-way match is perfectly clean: 0/1,044 cases have any GR event, exactly as
the category definition requires. The `>20` bucket is well populated in both
3-way categories (761 + 122 = 883 candidates), far more than the 2-case
fixture-wide cap needs. Max GR count observed: **269**, on a "3-way, invoice
after GR" case.

### 1.5 Vendor cardinality (plan B3 item 6)

1,975 distinct vendors. Heavily skewed: the top vendor alone accounts for
14,471 cases (5.7% of the dataset); 437 vendors have exactly 1 case; 499
vendors fall in the 2-6 case range targeted for the sampler's vendor cap.
That 499 is comfortably enough to draw ~60-100 vendors from for a ~300-case
fixture at 2-6 cases each.

### 1.6 Timestamp pathologies (plan B3 item 7) — real exclusion category found

97.2% of events fall in 2018, 2.8% in 2019. The remainder (320 events, 0.02%)
carry clearly bogus dates — 1948, 1993, 2001, 2008, 2015-2017, 2020 — all
attached to `Vendor creates invoice` / `Vendor creates debit memo` events.
This reads as a sentinel/placeholder date used when the true invoice date is
absent upstream, not a real historical event. It touches **266 distinct
cases**. A stable-sort reconstruction would place these events first in the
sequence, corrupting the fold — **these 266 cases are excluded** (§2.1).

**Also found, not anticipated by name in the plan but matching its
description of "cases whose first event is not a PO creation":** 10,503
cases (4.2%) do not begin with `Create Purchase Order Item` or
`Create Purchase Requisition Item`. These are cases truncated at the log's
observation window — we see only the tail of a lifecycle that began before
logging started. Breakdown of what they start with instead: `Vendor creates
invoice` (3,458), `Record Service Entry Sheet` (2,158),
`Receive Order Confirmation` (1,700), `SRM: Created` (1,360),
`Record Goods Receipt` (1,121), and 14 smaller categories. **These 10,503
cases are excluded** (§2.1) — we cannot reconstruct a PO header we never
observed being created.

### 1.7 No quantity field (plan B3 item 8)

Confirmed: `EXPECTED_COLUMNS` (22 columns total) contains no quantity or
unit-of-measure field. Quantities are null in Session 1 per plan.

### 1.8 Missing-GR viability (plan B3 item 9) — MISSING GR stretch goal is viable

Of the 15,179 zero-GR cases across both 3-way categories, **566 already have
a `Clear Invoice` event** — i.e. the process closed and was paid without a
goods receipt ever being recorded. That is a genuine anomaly, not simply "the
case is still open" (which would be the innocent explanation for most of the
remaining ~14,613). 566 cases is a comfortable pool for a stretch-goal
exception type. Per your direction, this is **sampled for, not built for**
in Session 1 — Day 2 implements it only if PRICE VARIANCE is fully working
with evals green.

### 1.9 2-way match GR contamination (plan B3 item 10)

Confirmed clean: 0 of 1,044 two-way-match cases have any `Record Goods
Receipt` event. No anomaly to handle here.

### 1.10 Cumulative net worth (EUR) — opportunistic, item 11

**This resolves the amounts question more favourably than the published
prior failure (see `docs/PROJECT.md` §4.3/§4.5 discussion) suggested.**

The field is **not** a true per-event running total. For 247,102 of 251,734
cases (98.2%), it takes exactly one value across every event in the case —
including every GR and every invoice event in a case with 20+ of each. It is
the PO line item's total net order value, repeated on every row of that
case, not a per-document amount.

Verified directly: in a 20-plus-event periodic case (`2000000020_00001`,
monthly-style GRs and invoices across the year), the value is `155884.0` on
literally every `Record Goods Receipt` and `Record Invoice Receipt` row. In
15 sampled clean single-GR/single-invoice cases, GR value and invoice value
were identical in all 15.

For the 1.8% of cases where the value *does* vary within the case, the
change is tied to a `Change Price` event or, in a smaller number, to a value
that is exactly double the case's other value at one `Record Invoice
Receipt` event — worth flagging as a possible duplicate-invoice-like
pattern for a later session, though duplicate invoice is deferred.

**Decision, consistent with the 90-minute timebox and your framing that
amounts-authored is the expected outcome:**

- The case-level total order value **is log-derived** — pulled from this
  field, once per case (using the single dominant value; for the 1.8% of
  cases with more than one distinct value, the value observed at the last
  event before the first `Change Price`, i.e. the original order value, is
  used).
- The **split of that total across multiple GR/invoice documents** within a
  case is authored — there is no field that carries a per-document amount,
  and the prior team's documented failure is explained exactly by this: they
  were looking for a signal that isn't there.
- Single-GR/single-invoice cases (the majority) need no split: the one GR
  and the one invoice both take the case's log-derived total directly. Only
  multi-document cases require an authored split.

This changes the field-group provenance table in §3 below: `NetPriceAmount`
on the PO item is **log-derived**, not authored. Only the
per-document (GR/invoice) monetary fields are authored, and only where a
case has more than one GR or more than one invoice.

#### 1.10.1 Hand-check finding: per-event unreliability in batch-imported
service cases (found during §5 hand-check, case `4508063534_00001`)

The hand-check gate (§5) caught something reconnaissance's 15-case spot
check missed. In `4508063534_00001` (102 goods receipts, a bulk import by
`batch_06` of ~100+ `Record Goods Receipt` events within a four-minute
window, each paired with a `Record Service Entry Sheet` event), the
`Cumulative net worth (EUR)` value is **not constant** the way the
20-plus-event periodic case in §1.10 was:

- `Create Purchase Order Item` and all 103 `Record Service Entry Sheet`
  events agree exactly: `9.0` throughout.
- Individual `Record Goods Receipt` events show wildly different values in
  the same case -- `131.0`, `18.0`, `206.0`, `384.0`, `56.0`, `309.0`, and so
  on -- none of which are sub-amounts of a 9.0 total; several *exceed* it by
  40x.

**This does not indicate a bug in the renderer -- it validates the
conservative design already in place.** `render.py` derives the case total
from the *first* chronological event (always the creation event, since
window-truncated cases are already excluded -- §2.1) and never reads
individual `Record Goods Receipt` values as authoritative; the per-document
split for multi-GR cases is always tagged `authored`, precisely because the
per-event field cannot be trusted. Had the renderer instead trusted each
GR's own field value directly -- an approach that looked tempting before
this case was hand-checked -- it would have fabricated a goods-receipt
amount of `384.0` against a `9.0` order, an obviously wrong number wearing
the costume of log-derived data.

**Scope check:** the *other* `>20`-bucket case in the fixture
(`4507003477_00010`, 33 goods receipts) was checked for the same pattern and
is perfectly constant (`20692.0` on every one of its 37 events). The
fluctuation is not universal -- it appears specific to bulk-imported
Service-type items with paired Service Entry Sheet events, not to
high-cardinality cases in general. No renderer change was needed; this
finding is recorded because the project's honesty requirement (§4.4)
means a surprising thing found during verification gets written down, not
quietly absorbed.

### 1.11 Schema-supporting facts, gathered alongside the required items

- `case Company`: 4 values, 99.6% `companyID_0000`. `companyID_0003` has
  exactly 1,044 cases — the same count as 2-way match, suggesting that
  category is concentrated in one subsidiary.
- `case Source`: single value (`sourceSystemID_0000`) throughout — not a
  useful discriminator.
- `case Purch. Doc. Category name`: single value (`Purchase order`)
  throughout.
- `case Document Type`: `Standard PO` (248,755), `Framework order` (1,539),
  `EC Purchase order` (1,440).
- `case Item Type`: `Standard` (220,186), `Consignment` (14,498, exactly
  matching the Consignment *category* count — clean 1:1), `Service`
  (5,838), `Third-party` (5,490), `Subcontracting` (4,678), `Limit` (1,044,
  exactly matching the 2-way-match count — another clean 1:1).
- `GR-Based Inv. Verif.` vs `Item Category`: perfectly clean 1:1 mapping
  (True only for "invoice after GR"). Confirms `InvoiceIsGoodsReceiptBased`
  is a lossless derivation.
- `Goods Receipt` (case-level expectation flag) vs `Item Category`: also
  clean 1:1 (True for both 3-way categories, False only for 2-way). This is
  an *expectation* flag, distinct from whether a GR event actually occurred
  — consistent with §1.4 showing some Consignment/3-way cases with zero
  actual GR events despite the flag being True.
- PO items per Purchasing Document: median 1, mean 3.3, max **429**. 63% of
  documents have exactly one item; a long tail runs very high. Confirms the
  B4 design decision to build PO headers once per document, not once per
  case.

---

## 2. Exclusions

Applied before sampling, each counted and never silently dropped, per plan.

### 2.1 Exclusion rules and counts

| Rule | Cases excluded | Rationale |
|---|---|---|
| Timestamp-sentinel contamination | 266 | Bogus dates (1948/1993/2001/2008/...) attached to invoice events would corrupt the stable-sort reconstruction (§1.6) |
| Window-truncated (no creation event first) | 10,503 | PO header was created before the log's observation window began; cannot be reconstructed (§1.6) |
| Overlap between the two rules | 257 | A case with only corrupted-timestamp events plausibly also lacks a real creation event |
| **Total excluded (deduplicated)** | **10,512** | 4.18% of 251,734 |

Computed programmatically by `derive/profile.py` (`timestamp_sentinel_cases`,
`window_truncated_cases`), confirming the overlap by set intersection rather
than assuming the two rules are independent.

251,734 − 10,512 = **241,222 eligible cases** remain, comfortably
supporting the 300-case sample.

**Checkpoint status:** the plan's three-hour hard checkpoint (acquisition +
reconnaissance + exclusions) was cleared at 16:30 UTC, 27 minutes after the
16:03 UTC session start -- well inside budget. The section 4.5 fallback
(hand-author ~60 cases, drop BPIC) was not invoked.

---

## 3. Document schema — SAP OData shape

Entities and fields modelled on the S/4HANA procurement APIs
(`API_PURCHASEORDER_PROCESS_SRV`, `API_MATERIAL_DOCUMENT_SRV`,
`API_SUPPLIERINVOICE_PROCESS_SRV`).

**Verified during Session 1** against a community-maintained field mirror of
`API_PURCHASEORDER_PROCESS_SRV` (no live Business Accelerator Hub tenant was
available for this project). This caught one real error: an earlier draft of
this schema included a `NetAmount` field on `A_PurchaseOrderItem`. **No such
field exists** -- the real entity carries only `NetPriceAmount` and
`NetPriceQuantity`. Fixed by removing `NetAmount`; `NetPriceAmount` now
carries the case's whole log-derived order value (see §1.10), since without
quantity data (null in Session 1, §1.7) there is no way to break it into a
true per-unit price. This is exactly the scenario the two-tier fixture split
(docs/PROJECT.md §6.1) exists for: `fixtures/rendered/` is re-issuable, so
the fix was a re-render, not an uncorrectable frozen mistake.
`A_MaterialDocumentItem`'s fields were also verified against the same
source and matched exactly.

| Entity | Key fields |
|---|---|
| `A_PurchaseOrder` | `PurchaseOrder`, `CompanyCode`, `PurchaseOrderType`, `Supplier`, `PurchasingOrganization`, `PurchasingGroup`, `DocumentCurrency`, `PurchaseOrderDate`, `CreatedByUser` |
| `A_PurchaseOrderItem` | `PurchaseOrder`, `PurchaseOrderItem`, `Material`, `MaterialGroup`, `Plant`, `OrderQuantity`, `PurchaseOrderQuantityUnit`, `NetPriceAmount`, `DocumentCurrency`, `GoodsReceiptIsExpected`, `InvoiceIsGoodsReceiptBased`, `IsCompletelyDelivered`, `IsFinallyInvoiced`, `PurchaseOrderItemCategory`, `AccountAssignmentCategory` |
| `A_MaterialDocumentHeader` + `A_MaterialDocumentItem`, denormalised | `MaterialDocumentYear`, `MaterialDocument`, `MaterialDocumentItem`, `GoodsMovementType` (101/102), `DocumentDate`, `PostingDate`, `CreatedByUser`, `PurchaseOrder`, `PurchaseOrderItem`, `QuantityInEntryUnit`, `EntryUnit`, `Plant`, plus `ReversesMaterialDocument` (authored -- §3.3) |
| `A_SupplierInvoice` + `A_SupplierInvoiceItemPurOrdRef`, denormalised | `SupplierInvoice`, `FiscalYear`, `SupplierInvoiceItem`, `CompanyCode`, `DocumentDate`, `PostingDate`, `InvoicingParty`, `SupplierInvoiceIDByInvcgParty`, `PurchaseOrder`, `PurchaseOrderItem`, `QuantityInPurchaseOrderUnit`, `SupplierInvoiceItemAmount`, `DocumentCurrency`, `PaymentTerms`, `ReverseDocument`, plus `ReferencesMaterialDocument` (authored -- §3.2) |

The header+item entity pairs are denormalised into single flat entries per
the module docstring in `src/docket/derive/render.py`: within one rendered
line item, a given material document or supplier invoice header always
belongs to exactly one item, so the normalisation SAP needs across many PO
items doesn't apply once the fixture is split one-file-per-line-item.
`SupplierInvoiceIDByInvcgParty` (the supplier's own invoice number, distinct
from the internal document number) is what duplicate-invoice detection would
turn on; kept even though that exception type is deferred. It is a
**surrogate** value in this fixture (`Provenance.SURROGATE`), not
log-derived -- the source log carries no field distinguishing it from the
internal key.
`InvoiceIsGoodsReceiptBased` maps directly and losslessly onto `GR-Based Inv.
Verif.` (§1.11).

### 3.1 Field-group provenance

| Field group | Provenance | Notes |
|---|---|---|
| PO identity, classification, vendor, company, document type, spend classification | `log-derived` | Case attributes, direct |
| Item Category / match flags (`GoodsReceiptIsExpected`, `InvoiceIsGoodsReceiptBased`) | `log-derived` | Clean 1:1 mapping confirmed §1.11 |
| Document counts, ordering, timestamps, acting user | `log-derived` | From the event sequence directly; 607 human / 20 batch users distinguished |
| PO item `NetPriceAmount` (case total) | `log-derived` | Revised finding, §1.10 — pulled from `Cumulative net worth (EUR)`, not authored |
| Individual GR / invoice monetary amount, where a case has >1 GR or >1 invoice | `authored` | No per-document signal exists in the log (§1.10); split of the log-derived total |
| Individual GR / invoice monetary amount, where a case has exactly 1 GR and 1 invoice | `log-derived` | Equal to the case total, no split needed |
| Quantity, unit of measure (all) | `null` (Session 1) | No quantity field in the source (§1.7); authored in Session 2 |
| Material, Plant, StorageLocation | `null` | No source; left null rather than invented |
| Currency | `EUR` throughout | Source's own normalisation across ~60 subsidiaries, not this project's choice. Values are anonymised by linear translation per the 4TU record — not real euro amounts even where log-derived. |

### 3.2 Multi-GR / multi-invoice matching assumption

The log carries no field linking a specific GR to the invoice that covers
it. Two options considered, per plan:

1. Don't match them — model GRs and invoices as two collections each
   referencing the PO item only, reconciling through the GR/IR clearing
   account. Faithful to the source, invents nothing.
2. Match positionally for `GR-Based Inv. Verif. = True` items (where SAP
   genuinely requires the invoice to reference a specific GR): k-th invoice
   references k-th GR in time order.

**Decision: (1) by default, (2) only for `GR-Based Inv. Verif. = True`
items, tagged `authored` in the rendered document.** Option 2 is inference,
not observation.

### 3.3 Reversal handling

`Cancel Goods Receipt` / `Cancel Invoice Receipt` are rendered as **reversal
documents** (movement type 102 against 101), never as deletions of the
original — preserving the audit trail the agent is meant to reason over.

---

## 4. Stratified sample allocation

Per plan: 110 / 110 / 50 / 30 across the four `Item Category` values,
sub-stratified by GR-count bucket, `>20` capped at 2 cases fixture-wide,
vendor cap of 2-6 cases per vendor. Hash-based selection
(`sha256(case_id + salt)`) for reproducibility independent of row order and
library RNG implementation.

Exact per-bucket counts and the final selected case-ID list are recorded in
`fixtures/frozen/FROZEN.md` once the selection is frozen (last step of the
session, per plan — after the hand-check, not before).
