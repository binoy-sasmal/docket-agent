"""Tests for the sampler's pure logic: allocation validation and hash-based
ranking. Tests that need the full ~500MB raw log (the actual select_sample()
run) belong in the slow suite instead -- these run on every push.
"""

from __future__ import annotations

from docket.derive.sample import (
    ALLOCATION,
    CATEGORY_TARGETS,
    _selection_rank,
    _validate_allocation,
)


def test_allocation_is_internally_consistent() -> None:
    # _validate_allocation() runs at import time already (it would have
    # raised on `import docket.derive.sample` if the table were wrong) --
    # this test exists so a future edit to ALLOCATION that breaks the
    # invariant fails in CI with a clear name, not just "collection error".
    _validate_allocation()


def test_allocation_totals_300() -> None:
    assert sum(sum(b.values()) for b in ALLOCATION.values()) == 300


def test_allocation_gt20_bucket_capped_at_two_fixture_wide() -> None:
    total = sum(buckets.get(">20", 0) for buckets in ALLOCATION.values())
    assert total == 2


def test_every_category_target_has_an_allocation() -> None:
    assert set(ALLOCATION.keys()) == set(CATEGORY_TARGETS.keys())


def test_selection_rank_is_deterministic() -> None:
    a = _selection_rank("4507004931_00020")
    b = _selection_rank("4507004931_00020")
    assert a == b


def test_selection_rank_differs_by_case_id() -> None:
    a = _selection_rank("4507004931_00020")
    b = _selection_rank("4507004931_00030")
    assert a != b
