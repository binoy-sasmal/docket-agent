"""Reconnaissance over the full BPIC 2019 log.

Findings from running this module are recorded in docs/DERIVATION.md section
1. This module is the reproducible form of that reconnaissance -- re-run it
to regenerate the same numbers, rather than trusting the prose summary.

GR_COUNT_BUCKETS below is shared with sample.py so the sub-stratification
boundaries used for sampling are provably the same ones reconnaissance was
run against.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from docket.derive.load import load_raw

EXPECTED_PURCHASE_DOCUMENTS = 76_349
EXPECTED_CASES = 251_734
EXPECTED_EVENTS = 1_595_923
EXPECTED_ACTIVITIES = 42

CREATION_ACTIVITIES = {"Create Purchase Order Item", "Create Purchase Requisition Item"}
SANE_YEARS = {2018, 2019}


def gr_bucket(n: int) -> str:
    """Shared bucketing rule -- sample.py imports this so sub-stratification
    uses exactly the boundaries reconnaissance was measured against.
    """
    if n == 0:
        return "0"
    if n == 1:
        return "1"
    if n <= 5:
        return "2-5"
    if n <= 20:
        return "6-20"
    return ">20"


@dataclass(frozen=True)
class FileIdentity:
    purchase_documents: int
    cases: int
    events: int
    activities: int

    @property
    def matches_expected(self) -> bool:
        return (
            self.purchase_documents == EXPECTED_PURCHASE_DOCUMENTS
            and self.cases == EXPECTED_CASES
            and self.events == EXPECTED_EVENTS
            and self.activities == EXPECTED_ACTIVITIES
        )


def check_file_identity(df: pd.DataFrame) -> FileIdentity:
    return FileIdentity(
        purchase_documents=df["case Purchasing Document"].nunique(),
        cases=df["case concept:name"].nunique(),
        events=len(df),
        activities=df["event concept:name"].nunique(),
    )


def case_level_frame(df: pd.DataFrame) -> pd.DataFrame:
    """One row per case: category, vendor, and GR/IR counts. This is the
    frame sample.py builds its stratification on.
    """
    case_cat = df.groupby("case concept:name", observed=True)["case Item Category"].first()
    case_vendor = df.groupby("case concept:name", observed=True)["case Vendor"].first()

    gr = df[df["event concept:name"] == "Record Goods Receipt"]
    ir = df[df["event concept:name"] == "Record Invoice Receipt"]
    gr_counts = gr.groupby("case concept:name", observed=True).size()
    ir_counts = ir.groupby("case concept:name", observed=True).size()

    all_cases = case_cat.index
    result = pd.DataFrame(
        {
            "category": case_cat,
            "vendor": case_vendor,
            "gr_count": gr_counts.reindex(all_cases, fill_value=0),
            "ir_count": ir_counts.reindex(all_cases, fill_value=0),
        }
    )
    result["gr_bucket"] = result["gr_count"].apply(gr_bucket)
    return result


def timestamp_sentinel_cases(df: pd.DataFrame) -> set[str]:
    """Cases touched by an event outside {2018, 2019} -- see
    docs/DERIVATION.md section 1.6. These carry sentinel/placeholder dates
    (1948, 1993, ...) that would corrupt a stable-sort reconstruction.
    """
    anomalous = df[~df["event time:timestamp"].dt.year.isin(SANE_YEARS)]
    return set(anomalous["case concept:name"].unique())


def window_truncated_cases(df: pd.DataFrame) -> set[str]:
    """Cases whose first event (by timestamp) is not a creation event --
    see docs/DERIVATION.md section 1.6. Truncated at the log's observation
    window; the PO header context was never observed.
    """
    first_events = (
        df.sort_values("event time:timestamp")
        .groupby("case concept:name", observed=True)["event concept:name"]
        .first()
    )
    truncated = first_events[~first_events.isin(CREATION_ACTIVITIES)]
    return set(truncated.index)


def missing_gr_but_cleared_cases(df: pd.DataFrame) -> set[str]:
    """3-way-category cases with zero GR events that nonetheless reached
    Clear Invoice -- the genuine anomaly pool behind the MISSING GR stretch
    goal (docs/DERIVATION.md section 1.8), as opposed to cases still open.
    """
    case_cat = df.groupby("case concept:name", observed=True)["case Item Category"].first()
    gr = df[df["event concept:name"] == "Record Goods Receipt"]
    gr_counts = gr.groupby("case concept:name", observed=True).size()
    zero_gr_cases = case_cat.index.difference(gr_counts.index)

    threeway_zero_gr = case_cat.loc[zero_gr_cases]
    threeway_zero_gr = threeway_zero_gr[
        threeway_zero_gr.isin(["3-way match, invoice after GR", "3-way match, invoice before GR"])
    ]

    clear = df[df["event concept:name"] == "Clear Invoice"]
    cleared_cases = set(clear["case concept:name"].unique())

    return {c for c in threeway_zero_gr.index if c in cleared_cases}


if __name__ == "__main__":
    frame = load_raw()

    identity = check_file_identity(frame)
    print(f"File identity matches docs/PROJECT.md section 4.1: {identity.matches_expected}")
    print(identity)

    cases = case_level_frame(frame)
    print("\nItem Category distribution:")
    print(cases["category"].value_counts())

    print("\nGR-bucket by category:")
    print(cases.groupby(["category", "gr_bucket"], observed=True).size().unstack(fill_value=0))

    sentinel = timestamp_sentinel_cases(frame)
    truncated = window_truncated_cases(frame)
    overlap = sentinel & truncated
    print(f"\nTimestamp-sentinel cases: {len(sentinel):,}")
    print(f"Window-truncated cases: {len(truncated):,}")
    print(f"Overlap between the two: {len(overlap):,}")
    print(f"Total excluded (deduplicated): {len(sentinel | truncated):,}")

    missing_gr = missing_gr_but_cleared_cases(frame)
    print(f"\nGenuine missing-GR (closed without GR) pool: {len(missing_gr):,}")
