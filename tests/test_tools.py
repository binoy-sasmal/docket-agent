"""Tests for the read-only OData-shaped fixture tool layer."""

from __future__ import annotations

import pytest

from docket.fixture_store import FixtureLookupError, FrozenFixtureStore
from docket.tools.odata import ReadOnlyODataTools, ToolAccessDenied


def test_fixture_store_loads_only_frozen_selected_cases() -> None:
    store = FrozenFixtureStore()

    assert "4507000477_00060" in store.selected_case_ids
    document = store.load_case("4507000477_00060")

    assert document.source_case_id == "4507000477_00060"
    with pytest.raises(FixtureLookupError, match="not in the frozen selection"):
        store.load_case("not-a-frozen-case")


def test_odata_tools_return_purchase_order_item_and_related_documents() -> None:
    tools = ReadOnlyODataTools()

    item = tools.get_A_PurchaseOrderItem("4507000477", "00060")
    goods_receipts = tools.list_A_MaterialDocumentItem("4507000477", "00060")
    invoices = tools.list_A_SupplierInvoiceItemPurOrdRef("4507000477", "00060")

    assert item.NetPriceAmount == goods_receipts[0].Amount
    assert item.NetPriceAmount == invoices[0].SupplierInvoiceItemAmount
    assert goods_receipts[0].MaterialDocument == "MD4492535791618"
    assert invoices[0].SupplierInvoice == "SI4492535791620"


def test_odata_tools_record_read_trajectory() -> None:
    tools = ReadOnlyODataTools()

    tools.get_A_PurchaseOrderItem("4507075965", "00050")

    assert [call.name for call in tools.tool_calls] == ["get_A_PurchaseOrderItem"]
    assert tools.tool_calls[0].arguments == {
        "PurchaseOrder": "4507075965",
        "PurchaseOrderItem": "00050",
    }


def test_odata_tools_reject_non_allowlisted_tool_names() -> None:
    tools = ReadOnlyODataTools()

    with pytest.raises(ToolAccessDenied, match="not allowlisted"):
        tools._record("post_supplier_invoice", SupplierInvoice="SI1")
