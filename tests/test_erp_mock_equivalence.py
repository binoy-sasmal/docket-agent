"""Connected mode against the CAP mock ERP gives the same results as frozen mode.

Needs the service running and DOCKET_ERP_URL pointing at it, e.g.

    python tools/export_erp_mock_data.py
    (cd erp-mock && npm ci && npm start)
    DOCKET_ERP_URL=http://localhost:4004/odata/v4/procurement pytest -m erp

Skipped otherwise; CI runs it in its own job with the service started.

Covers every one of the 300 frozen-selected cases, not only the golden 30:
the documents each lookup returns, and the investigation, reconciliation,
policy decision and proposal the deterministic pipeline builds from them.
"""

from __future__ import annotations

import os
from dataclasses import asdict

import httpx
import pytest

from docket.fixture_store import FrozenFixtureStore
from docket.graph.skeleton import CaseKey, run_case
from docket.tools.odata import ReadOnlyODataTools
from docket.tools.odata_http import HttpODataTools

ERP_URL = os.environ.get("DOCKET_ERP_URL", "")

pytestmark = [
    pytest.mark.erp,
    pytest.mark.skipif(not ERP_URL, reason="DOCKET_ERP_URL not set; the CAP mock is not running"),
]

CASES = [CaseKey(*case_id.split("_")) for case_id in FrozenFixtureStore().selected_case_ids]


def _ids(case: CaseKey) -> str:
    return f"{case.purchase_order}_{case.purchase_order_item}"


@pytest.fixture(scope="module")
def frozen() -> ReadOnlyODataTools:
    return ReadOnlyODataTools()


@pytest.fixture(scope="module")
def connected() -> HttpODataTools:
    return HttpODataTools(ERP_URL)


def test_the_service_serves_every_frozen_case(connected: HttpODataTools) -> None:
    assert len(CASES) == 300
    for case in CASES:
        connected.get_A_PurchaseOrderItem(case.purchase_order, case.purchase_order_item)


@pytest.mark.parametrize("case", CASES, ids=_ids)
def test_documents_match_frozen_mode(
    case: CaseKey, frozen: ReadOnlyODataTools, connected: HttpODataTools
) -> None:
    po, item = case.purchase_order, case.purchase_order_item

    assert connected.get_A_PurchaseOrder(po) == frozen.get_A_PurchaseOrder(po)

    assert connected.get_A_PurchaseOrderItem(po, item) == frozen.get_A_PurchaseOrderItem(po, item)
    # Same documents; an ERP returns them in query order (posting date, key).
    assert set(connected.list_A_MaterialDocumentItem(po, item)) == set(
        frozen.list_A_MaterialDocumentItem(po, item)
    )
    assert set(connected.list_A_SupplierInvoiceItemPurOrdRef(po, item)) == set(
        frozen.list_A_SupplierInvoiceItemPurOrdRef(po, item)
    )


@pytest.mark.parametrize("case", CASES, ids=_ids)
def test_the_pipeline_decides_identically_in_both_modes(case: CaseKey) -> None:
    frozen_run = run_case(case, ReadOnlyODataTools())
    connected_run = run_case(case, HttpODataTools(ERP_URL))

    assert connected_run.investigation.tool_calls == frozen_run.investigation.tool_calls
    assert connected_run.policy == frozen_run.policy
    assert connected_run.proposal.disposition == frozen_run.proposal.disposition
    assert connected_run.proposal.can_post is False

    # Same claims with the same text, citing the same documents. A claim
    # lists its evidence in the order the documents arrived, which differs
    # between the fixtures and an ERP query, so evidence is compared as a set.
    for frozen_side, connected_side in (
        (frozen_run.reconciliation, connected_run.reconciliation),
        (frozen_run.proposal, connected_run.proposal),
    ):
        frozen_fields, connected_fields = asdict(frozen_side), asdict(connected_side)
        frozen_claims, connected_claims = (
            frozen_fields.pop("claims"),
            connected_fields.pop("claims"),
        )
        assert _normalised(connected_claims) == _normalised(frozen_claims)
        assert connected_fields == frozen_fields


def _normalised(claims: list[dict[str, object]]) -> list[tuple[str, frozenset[str]]]:
    return sorted(
        (str(claim["text"]), frozenset(repr(e) for e in claim["evidence"]))  # type: ignore[union-attr]
        for claim in claims
    )


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
def test_the_service_refuses_every_write(method: str) -> None:
    po = CASES[0].purchase_order
    url = f"{ERP_URL}/A_PurchaseOrder" if method == "POST" else f"{ERP_URL}/A_PurchaseOrder('{po}')"
    response = httpx.request(method, url, json={"Supplier": "attacker"}, timeout=10)
    assert response.status_code == 405
    assert HttpODataTools(ERP_URL).get_A_PurchaseOrder(po).Supplier != "attacker"
