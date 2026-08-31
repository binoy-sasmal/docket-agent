"""Tests for the amount-splitting and rendering logic in derive/render.py.

These exercise the pure helper functions directly rather than the full
load-CSV-then-render pipeline, which needs the ~500MB raw file and is
covered instead by the slow, full-log checks (docs/DERIVATION.md, run via
`python -m docket.derive.render`).
"""

from __future__ import annotations

from decimal import Decimal

from docket.derive.render import _split_amount


def test_split_amount_single_part_is_the_whole_total() -> None:
    assert _split_amount(Decimal("100.00"), 1) == [Decimal("100.00")]


def test_split_amount_sums_back_to_the_total_exactly() -> None:
    total = Decimal("100.00")
    parts = _split_amount(total, 3)
    assert sum(parts) == total


def test_split_amount_remainder_goes_to_the_last_part() -> None:
    # 100.00 / 3 = 33.33 with 0.01 left over -- the split must not lose or
    # gain a cent (docs/DERIVATION.md 1.10: the split is authored, but it
    # must still be an honest partition of the log-derived total).
    parts = _split_amount(Decimal("100.00"), 3)
    assert parts == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]


def test_split_amount_handles_zero_total() -> None:
    # Real cases in the fixture have a zero NetPriceAmount (docs/DERIVATION.md --
    # 32 of the 300 selected cases). Splitting zero must not raise.
    parts = _split_amount(Decimal("0"), 5)
    assert parts == [Decimal("0")] * 5
    assert sum(parts) == Decimal("0")


def test_split_amount_of_zero_parts_is_empty() -> None:
    assert _split_amount(Decimal("100.00"), 0) == []
