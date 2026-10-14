"""Offline tests for the connected-mode OData adapter, against a stub transport.

The adapter must return exactly the models the frozen fixture tools return,
send only reads, and record the same tool calls. The live equivalence check
against the CAP service is in test_erp_mock_equivalence.py.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
import pytest

from docket.fixture_store import FixtureLookupError
from docket.graph.langgraph_app import build_docket_graph
from docket.tools.injection import InjectionOverlay
from docket.tools.odata import ReadOnlyODataTools
from docket.tools.odata_http import HttpODataTools

PO, ITEM = "4507000477", "00060"


def _fixture_tools() -> ReadOnlyODataTools:
    return ReadOnlyODataTools()


def _as_odata(model: object) -> dict[str, object]:
    """A row the way CAP sends it with IEEE754Compatible: decimals as strings,
    the acting user flattened into CreatedByUser_* columns, and the OData
    annotations a real response carries."""
    row = json.loads(model.model_dump_json())  # type: ignore[attr-defined]
    user = row.pop("CreatedByUser", None)
    if isinstance(user, dict):
        row.update({f"CreatedByUser_{key}": value for key, value in user.items()})
    return {"@odata.etag": 'W/"x"', **row}


def _service(seen: list[httpx.Request], *, page_size: int | None = None) -> httpx.MockTransport:
    fixtures = _fixture_tools()
    po = fixtures.get_A_PurchaseOrder(PO)
    item = fixtures.get_A_PurchaseOrderItem(PO, ITEM)
    grs = fixtures.list_A_MaterialDocumentItem(PO, ITEM)
    invoices = fixtures.list_A_SupplierInvoiceItemPurOrdRef(PO, ITEM)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = unquote(request.url.path)
        if path.endswith(f"A_PurchaseOrder('{PO}')"):
            return httpx.Response(200, json=_as_odata(po))
        if path.endswith(f"A_PurchaseOrderItem(PurchaseOrder='{PO}',PurchaseOrderItem='{ITEM}')"):
            return httpx.Response(200, json=_as_odata(item))
        rows = {
            "A_MaterialDocumentItem": grs,
            "A_SupplierInvoiceItemPurOrdRef": invoices,
        }.get(path.rsplit("/", 1)[-1])
        if rows is not None:
            wanted = f"PurchaseOrder eq '{PO}' and PurchaseOrderItem eq '{ITEM}'"
            query = parse_qs(urlsplit(str(request.url)).query)
            if query.get("$filter", [wanted]) != [wanted]:
                rows = ()  # a real service filters; anything else matches nothing here
            values = [_as_odata(r) for r in rows]
            skip = int(parse_qs(urlsplit(str(request.url)).query).get("$skip", ["0"])[0])
            if page_size is None:
                return httpx.Response(200, json={"value": values})
            page = values[skip : skip + page_size]
            body: dict[str, object] = {"value": page}
            if skip + page_size < len(values):
                body["@odata.nextLink"] = f"{path.rsplit('/', 1)[-1]}?$skip={skip + page_size}"
            return httpx.Response(200, json=body)
        return httpx.Response(404, json={"error": {"code": "404", "message": "Not Found"}})

    return httpx.MockTransport(handler)


def _http_tools(seen: list[httpx.Request], **kwargs: object) -> HttpODataTools:
    return HttpODataTools(
        "http://erp.test/odata/v4/procurement",
        transport=_service(seen, **kwargs),  # type: ignore[arg-type]
    )


def test_adapter_returns_the_same_models_as_the_fixture_tools() -> None:
    seen: list[httpx.Request] = []
    http, fixtures = _http_tools(seen), _fixture_tools()

    assert http.get_A_PurchaseOrder(PO) == fixtures.get_A_PurchaseOrder(PO)
    assert http.get_A_PurchaseOrderItem(PO, ITEM) == fixtures.get_A_PurchaseOrderItem(PO, ITEM)
    assert set(http.list_A_MaterialDocumentItem(PO, ITEM)) == set(
        fixtures.list_A_MaterialDocumentItem(PO, ITEM)
    )
    assert set(http.list_A_SupplierInvoiceItemPurOrdRef(PO, ITEM)) == set(
        fixtures.list_A_SupplierInvoiceItemPurOrdRef(PO, ITEM)
    )


def test_adapter_sends_only_reads_with_exact_decimals_requested() -> None:
    seen: list[httpx.Request] = []
    tools = _http_tools(seen)
    tools.get_A_PurchaseOrder(PO)
    tools.list_A_MaterialDocumentItem(PO, ITEM)

    assert {r.method for r in seen} == {"GET"}
    # Decimals as strings, so no amount passes through a binary float.
    assert all("IEEE754Compatible=true" in r.headers["accept"] for r in seen)
    query = parse_qs(urlsplit(str(seen[1].url)).query)
    assert query["$filter"] == [f"PurchaseOrder eq '{PO}' and PurchaseOrderItem eq '{ITEM}'"]
    # OData requires %20 for a space; the form-encoded `+` is rejected by CAP.
    raw = seen[1].url.query.decode()
    assert "+" not in raw and "PurchaseOrder%20eq%20" in raw
    assert "$select" in query and "Amount" in query["$select"][0]


def test_adapter_follows_server_paging() -> None:
    seen: list[httpx.Request] = []
    tools = _http_tools(seen, page_size=1)
    receipts = tools.list_A_MaterialDocumentItem(PO, ITEM)

    assert len(receipts) == len(_fixture_tools().list_A_MaterialDocumentItem(PO, ITEM))
    assert len(seen) == len(receipts)


def test_a_missing_document_raises_the_same_error_as_frozen_mode() -> None:
    with pytest.raises(FixtureLookupError, match="not found"):
        _http_tools([]).get_A_PurchaseOrder("4599999999")


def test_quotes_in_keys_are_escaped_not_injected() -> None:
    seen: list[httpx.Request] = []
    with pytest.raises(FixtureLookupError):
        _http_tools(seen).list_A_MaterialDocumentItem("x' or 1 eq 1 or 'a", ITEM)
    query = parse_qs(urlsplit(str(seen[0].url)).query)
    assert query["$filter"][0].startswith("PurchaseOrder eq 'x'' or 1 eq 1 or ''a'")


def test_adapter_records_the_same_allowlisted_tool_calls() -> None:
    http, fixtures = _http_tools([]), _fixture_tools()
    for tools in (http, fixtures):
        tools.get_A_PurchaseOrder(PO)
        tools.list_A_SupplierInvoiceItemPurOrdRef(PO, ITEM)
    assert http.tool_calls == fixtures.tool_calls
    assert http.allowed_tool_names == fixtures.allowed_tool_names


def test_injection_overlays_are_refused_in_connected_mode() -> None:
    # Overlays are an eval instrument applied to in-memory fixture copies;
    # a connected run is never an eval run, so the combination is an error.
    overlay = InjectionOverlay(
        overlay_id="x", case_id=f"{PO}_{ITEM}", target="purchase_order_item_note", payload="p"
    )
    with pytest.raises(ValueError, match="overlays"):
        build_docket_graph(tools_factory=lambda: _http_tools([]), overlays=(overlay,))
