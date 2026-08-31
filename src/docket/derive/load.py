"""Load the BPIC 2019 CSV into a typed pandas DataFrame.

Column naming: the CSV uses "case <Field>" / "event <Field>" prefixes, not
the XES "case:<field>" convention. This module does not hardcode either
form -- it reads the header, asserts it against the expected set, and fails
loudly on mismatch (see EXPECTED_COLUMNS below).

Money: the monetary column serialises in scientific notation for some rows
(e.g. "2.8405633E7"). It is read as a string and converted via
decimal.Decimal, never via a pandas-inferred float64 -- a float round-trip
would silently lose precision before the value ever reaches the schema.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

CSV_PATH = Path(__file__).resolve().parents[3] / "data" / "raw" / "BPI_Challenge_2019.csv"

# As read directly from the file header on 2026-08-31.
EXPECTED_COLUMNS = [
    "eventID ",
    "case Spend area text",
    "case Company",
    "case Document Type",
    "case Sub spend area text",
    "case Purchasing Document",
    "case Purch. Doc. Category name",
    "case Vendor",
    "case Item Type",
    "case Item Category",
    "case Spend classification text",
    "case Source",
    "case Name",
    "case GR-Based Inv. Verif.",
    "case Item",
    "case concept:name",
    "case Goods Receipt",
    "event User",
    "event org:resource",
    "event concept:name",
    "event Cumulative net worth (EUR)",
    "event time:timestamp",
]

# Columns cast to pandas "category" dtype -- repeated string values, cast to
# keep the ~1.6M-row frame in a few hundred MB rather than several GB.
CATEGORICAL_COLUMNS = [
    "case Spend area text",
    "case Company",
    "case Document Type",
    "case Sub spend area text",
    "case Purch. Doc. Category name",
    "case Vendor",
    "case Item Type",
    "case Item Category",
    "case Spend classification text",
    "case Source",
    "case Name",
    "case GR-Based Inv. Verif.",
    "event User",
    "event org:resource",
    "event concept:name",
    "case Goods Receipt",
]


def load_raw(csv_path: Path = CSV_PATH, nrows: int | None = None) -> pd.DataFrame:
    """Load the CSV with header assertion, categorical casting, and the
    monetary column preserved as a string (never coerced to float).
    """
    # Read the monetary column as string explicitly so pandas never infers
    # float64 for it -- this is what protects the E-notation values.
    df = pd.read_csv(
        csv_path,
        dtype={"event Cumulative net worth (EUR)": "string"},
        nrows=nrows,
        # Not UTF-8: at least one byte (0x96, a Windows-1252 en-dash) is
        # invalid UTF-8. cp1252 is the standard fallback for text produced
        # on Windows in a European locale and decodes the file cleanly.
        encoding="cp1252",
    )

    actual_columns = list(df.columns)
    if actual_columns != EXPECTED_COLUMNS:
        missing = set(EXPECTED_COLUMNS) - set(actual_columns)
        extra = set(actual_columns) - set(EXPECTED_COLUMNS)
        raise ValueError(
            "CSV header does not match the expected column set.\n"
            f"Missing: {sorted(missing)}\nExtra: {sorted(extra)}\n"
            f"Full actual header: {actual_columns}"
        )

    for col in CATEGORICAL_COLUMNS:
        df[col] = df[col].astype("category")

    df["event time:timestamp"] = pd.to_datetime(
        df["event time:timestamp"], format="%d-%m-%Y %H:%M:%S.%f"
    )

    return df


if __name__ == "__main__":
    frame = load_raw()
    print(f"rows: {len(frame):,}")
    print(f"columns: {len(frame.columns)}")
    print(frame.dtypes)
