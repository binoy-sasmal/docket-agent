"""Full-log checks against the real ~500MB CSV. Marked slow -- these load
the entire file (a dozen-plus seconds each) and are not part of the fast
default suite that runs on every push. Run explicitly with:

    pytest -m slow

Covers docs/DERIVATION.md's headline numbers so a change to load.py,
profile.py, or sample.py that silently breaks reconnaissance is caught here
rather than only being noticed by re-reading the markdown.
"""

from __future__ import annotations

import pytest

from docket.derive.load import load_raw
from docket.derive.profile import (
    EXPECTED_ACTIVITIES,
    EXPECTED_CASES,
    EXPECTED_EVENTS,
    EXPECTED_PURCHASE_DOCUMENTS,
    check_file_identity,
    missing_gr_but_cleared_cases,
    timestamp_sentinel_cases,
    window_truncated_cases,
)
from docket.derive.render import render_case
from docket.derive.sample import select_sample
from docket.schema.procurement import RenderedLineItem

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def raw_frame():  # type: ignore[no-untyped-def]
    return load_raw()


def test_file_identity_matches_docs_project_md_section_4_1(raw_frame) -> None:  # type: ignore[no-untyped-def]
    identity = check_file_identity(raw_frame)
    assert identity.purchase_documents == EXPECTED_PURCHASE_DOCUMENTS
    assert identity.cases == EXPECTED_CASES
    assert identity.events == EXPECTED_EVENTS
    assert identity.activities == EXPECTED_ACTIVITIES


def test_exclusion_counts_match_docs_derivation_md_section_2_1(raw_frame) -> None:  # type: ignore[no-untyped-def]
    sentinel = timestamp_sentinel_cases(raw_frame)
    truncated = window_truncated_cases(raw_frame)
    assert len(sentinel) == 266
    assert len(truncated) == 10_503
    assert len(sentinel & truncated) == 257
    assert len(sentinel | truncated) == 10_512


def test_missing_gr_pool_matches_docs_derivation_md_section_1_8(raw_frame) -> None:  # type: ignore[no-untyped-def]
    assert len(missing_gr_but_cleared_cases(raw_frame)) == 566


def test_select_sample_produces_exactly_300_cases(raw_frame) -> None:  # type: ignore[no-untyped-def]
    result = select_sample(raw_frame)
    assert len(result.selected_case_ids) == 300
    for (category, bucket), actual in result.per_cell_actual.items():
        from docket.derive.sample import ALLOCATION

        assert actual == ALLOCATION[category][bucket], (
            f"{category}/{bucket}: got {actual}, wanted {ALLOCATION[category][bucket]}"
        )


def test_select_sample_is_deterministic_across_runs(raw_frame) -> None:  # type: ignore[no-untyped-def]
    first = select_sample(raw_frame)
    second = select_sample(raw_frame)
    assert first.selected_case_ids == second.selected_case_ids


def test_every_selected_case_renders_without_error(raw_frame) -> None:  # type: ignore[no-untyped-def]
    result = select_sample(raw_frame)
    for case_id in result.selected_case_ids:
        trace = raw_frame[raw_frame["case concept:name"] == case_id]
        doc = render_case(trace)
        assert isinstance(doc, RenderedLineItem)
        assert doc.source_case_id == case_id


def test_amount_conservation_across_every_selected_case(raw_frame) -> None:  # type: ignore[no-untyped-def]
    """Sum of non-reversal GR amounts, and sum of non-reversal invoice
    amounts, must each equal the case's NetPriceAmount whenever any exist --
    docs/DERIVATION.md 1.10's authored-split must be an honest partition.
    """
    result = select_sample(raw_frame)
    for case_id in result.selected_case_ids:
        trace = raw_frame[raw_frame["case concept:name"] == case_id]
        doc = render_case(trace)
        total = doc.purchase_order_item.NetPriceAmount

        gr_originals = [g for g in doc.goods_receipts if g.GoodsMovementType == "101"]
        if gr_originals:
            assert sum(g.Amount for g in gr_originals) == total, case_id

        iv_originals = [i for i in doc.invoices if i.ReverseDocument is None]
        if iv_originals:
            assert sum(i.SupplierInvoiceItemAmount for i in iv_originals) == total, case_id
