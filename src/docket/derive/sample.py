"""Stratified subsampling of ~300 line items from the eligible case pool.

Per docs/DERIVATION.md section 4 and the Session 1 plan:

- Allocation across Item Category: 110 / 110 / 50 / 30 (a deliberate
  flattening of the real distribution -- see docs/DERIVATION.md 1.2 -- with
  Consignment weighted down because it has no PO-level invoice at all and
  serves as a negative control, not a working case).
- Sub-stratified within each category by GR-count bucket
  (docket.derive.profile.gr_bucket), so the sample isn't ~90% trivial
  single-GR cases.
- The ">20" bucket capped at exactly 2 cases fixture-wide.
- A per-vendor cap so the fixture doesn't concentrate in a handful of
  vendors (docs/DERIVATION.md 1.5: the most common vendor alone accounts for
  5.7% of all cases).
- Hash-based selection, not df.sample(random_state=) -- ranking candidates
  within each cell by sha256(case_id + salt) is reproducible independent of
  row order, pandas version, and the numpy RNG implementation, which matters
  once the selection is content-hash-frozen.

The ALLOCATION table below is not computed by a generic solver at runtime --
it is the result of applying the stated rule (floor of ~10 cases per
populated bucket, ~5 for the 30-slot Consignment stratum, remainder to the
most populated bucket, >20 split 1/1 across the two 3-way categories to hit
the fixture-wide cap of 2) by hand against the exact bucket populations
found in reconnaissance (docs/DERIVATION.md section 1.4), and is asserted
against those populations at import time. Hardcoding the *result* rather
than the solver keeps the allocation reviewable by a human against the
recon numbers directly -- which matters more here than solver generality.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from docket.derive.load import load_raw
from docket.derive.profile import (
    case_level_frame,
    timestamp_sentinel_cases,
    window_truncated_cases,
)
from docket.schema.canonical import write_canonical_json

# Recomputed here from docs/DERIVATION.md section 1.4 for the assertion in
# _validate_allocation() below -- these are frozen numbers from a specific
# recon run, not re-derived at runtime (which would defeat the point of the
# assertion: it catches the allocation table drifting out of sync with the
# recon findings it was built from, not drift in the source data itself).
BUCKET_POPULATIONS: dict[str, dict[str, int]] = {
    "2-way match": {"0": 1044},
    "Consignment": {"0": 1032, "1": 12122, "2-5": 1307, "6-20": 37, ">20": 0},
    "3-way match, invoice after GR": {
        "0": 643,
        "1": 10294,
        "2-5": 2162,
        "6-20": 1322,
        ">20": 761,
    },
    "3-way match, invoice before GR": {
        "0": 14536,
        "1": 199385,
        "2-5": 6581,
        "6-20": 386,
        ">20": 122,
    },
}

CATEGORY_TARGETS: dict[str, int] = {
    "3-way match, invoice after GR": 110,
    "3-way match, invoice before GR": 110,
    "2-way match": 50,
    "Consignment": 30,
}

ALLOCATION: dict[str, dict[str, int]] = {
    "2-way match": {"0": 50},
    "Consignment": {"0": 5, "1": 15, "2-5": 5, "6-20": 5},
    "3-way match, invoice after GR": {"0": 10, "1": 70, "2-5": 10, "6-20": 19, ">20": 1},
    "3-way match, invoice before GR": {"0": 10, "1": 70, "2-5": 10, "6-20": 19, ">20": 1},
}

VENDOR_CAP = 6
"""Upper bound on cases drawn from a single vendor. Target range per plan is
2-6; this is enforced as a hard ceiling during selection, not a floor --
natural variation in the eligible pool supplies the lower end.
"""

HASH_SALT = "docket-bpic2019-session1"
"""Fixed salt for the selection-ranking hash. Changing this value changes
which cases get selected -- do not change it once a selection has been
frozen by freeze.py.
"""


def _validate_allocation() -> None:
    for category, target in CATEGORY_TARGETS.items():
        buckets = ALLOCATION[category]
        total = sum(buckets.values())
        if total != target:
            raise AssertionError(
                f"ALLOCATION[{category!r}] sums to {total}, expected {target}"
            )
        for bucket, count in buckets.items():
            available = BUCKET_POPULATIONS[category].get(bucket, 0)
            if count > available:
                raise AssertionError(
                    f"ALLOCATION[{category!r}][{bucket!r}] wants {count}, "
                    f"only {available} available per recon"
                )
    grand_total = sum(sum(b.values()) for b in ALLOCATION.values())
    if grand_total != 300:
        raise AssertionError(f"ALLOCATION grand total is {grand_total}, expected 300")
    gt20_total = sum(buckets.get(">20", 0) for buckets in ALLOCATION.values())
    if gt20_total != 2:
        raise AssertionError(f"'>20' bucket totals {gt20_total} fixture-wide, expected 2")


_validate_allocation()


def _selection_rank(case_id: str) -> str:
    """Hash-based rank key. Lower is selected first. Deterministic given
    HASH_SALT, independent of DataFrame row order or library RNG state.
    """
    return hashlib.sha256(f"{case_id}{HASH_SALT}".encode()).hexdigest()


@dataclass(frozen=True)
class SelectionResult:
    selected_case_ids: list[str]
    per_cell_actual: dict[tuple[str, str], int]
    excluded_count: int
    eligible_count: int


def select_sample(df: pd.DataFrame | None = None) -> SelectionResult:
    """Run the full exclusion -> stratification -> hash-ranked, vendor-capped
    selection pipeline and return the chosen case IDs plus the bookkeeping
    needed for the FROZEN.md provenance record freeze.py writes.
    """
    if df is None:
        df = load_raw()

    excluded = timestamp_sentinel_cases(df) | window_truncated_cases(df)
    cases = case_level_frame(df)
    eligible = cases.drop(index=sorted(excluded), errors="ignore")

    vendor_counts: dict[str, int] = {}
    selected: list[str] = []
    per_cell_actual: dict[tuple[str, str], int] = {}

    for category, buckets in ALLOCATION.items():
        for bucket, target in buckets.items():
            cell = eligible[
                (eligible["category"] == category) & (eligible["gr_bucket"] == bucket)
            ]
            ranked = sorted(cell.index, key=_selection_rank)

            picked = 0
            for case_id in ranked:
                if picked >= target:
                    break
                vendor = eligible.loc[case_id, "vendor"]
                if vendor_counts.get(vendor, 0) >= VENDOR_CAP:
                    continue
                selected.append(case_id)
                vendor_counts[vendor] = vendor_counts.get(vendor, 0) + 1
                picked += 1

            per_cell_actual[(category, bucket)] = picked

    return SelectionResult(
        selected_case_ids=sorted(selected),
        per_cell_actual=per_cell_actual,
        excluded_count=len(excluded),
        eligible_count=len(eligible),
    )


DERIVED_SELECTION_PATH = (
    Path(__file__).resolve().parents[3] / "fixtures" / "derived" / "selection" / "cases.json"
)


def write_selection(result: SelectionResult, path: Path) -> None:
    """Write the ordinary sampler output that a later, separate freeze step
    copies into the frozen selection -- this function never writes under the
    frozen path itself (tests/test_architecture.py enforces that no module
    under derive/ even references it).
    """
    payload = {
        "selected_case_ids": result.selected_case_ids,
        "excluded_count": result.excluded_count,
        "eligible_count": result.eligible_count,
        "per_cell_actual": {
            f"{category}::{bucket}": count
            for (category, bucket), count in sorted(result.per_cell_actual.items())
        },
        "hash_salt": HASH_SALT,
        "vendor_cap": VENDOR_CAP,
    }
    write_canonical_json(path, payload)


if __name__ == "__main__":
    result = select_sample()
    print(f"excluded: {result.excluded_count:,}")
    print(f"eligible: {result.eligible_count:,}")
    print(f"selected: {len(result.selected_case_ids)}")
    print()
    for (category, bucket), actual in result.per_cell_actual.items():
        target = ALLOCATION[category][bucket]
        status = "OK" if actual == target else "SHORT"
        print(f"{status:6} {category:35} {bucket:6} target={target:4} actual={actual:4}")

    write_selection(result, DERIVED_SELECTION_PATH)
    print(f"\nwrote {DERIVED_SELECTION_PATH}")
