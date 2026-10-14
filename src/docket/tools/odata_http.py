"""Connected mode: the same four read-only lookups over a live OData v4 service.

`HttpODataTools` implements `docket.tools.odata.ODataToolFacade` against an
OData service with SAP's entity shapes -- in this repository the CAP mock in
`erp-mock/`, which is seeded from the frozen fixtures. Frozen mode stays the
default everywhere, and the eval harness never uses this class: a test that
depends on a running server cannot be the ground truth.

It only ever sends GET. Decimals are requested as strings
(`IEEE754Compatible=true`), so no amount passes through a binary float on the
way in. Each request selects exactly the model's fields, because the schema
models reject unknown fields and an OData row carries annotations such as
`@odata.etag`. Lists are ordered by posting date then document key, the order
a query against an ERP would give; the frozen eval returns identical
dispositions and trajectories under that order (tests/test_erp_mock_equivalence.py).
"""

from __future__ import annotations

from typing import Any, ClassVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel

from docket.fixture_store import FixtureLookupError
from docket.schema.procurement import (
    AMaterialDocumentEntry,
    APurchaseOrder,
    APurchaseOrderItem,
    ASupplierInvoiceEntry,
)
from docket.tools.odata import ReadOnlyODataTools, ToolAccessDenied, ToolCall

_ACCEPT = "application/json;IEEE754Compatible=true"
_KEY_PREDICATE_CHARS = "()=,'"
_QUERY_SAFE = "',()"


def _literal(value: str) -> str:
    """An OData string literal. A quote inside the value is doubled, so a key
    can never close the literal and extend the query."""
    return "'" + value.replace("'", "''") + "'"


def _select(model: type[BaseModel]) -> str:
    """Every field of `model`, with a nested model (the acting user) named
    by its flattened columns, which is how OData services expose it."""
    names: list[str] = []
    for name, field in model.model_fields.items():
        nested = _nested_model(field.annotation)
        if nested is None:
            names.append(name)
        else:
            names.extend(f"{name}_{sub}" for sub in nested.model_fields)
    return ",".join(names)


def _nested_model(annotation: object) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _query(params: dict[str, str]) -> str:
    """An OData query string, encoded by hand. A space must be %20: OData
    services, CAP included, reject the `+` that form-encoding, and therefore
    httpx's `params=`, produces."""
    return "&".join(f"{name}={quote(value, safe=_QUERY_SAFE)}" for name, value in params.items())


class HttpODataTools:
    ALLOWED_TOOL_NAMES: ClassVar[frozenset[str]] = ReadOnlyODataTools.ALLOWED_TOOL_NAMES

    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(
            timeout=timeout_s, transport=transport, headers={"Accept": _ACCEPT}
        )
        self._tool_calls: list[ToolCall] = []

    @property
    def tool_calls(self) -> tuple[ToolCall, ...]:
        return tuple(self._tool_calls)

    @property
    def allowed_tool_names(self) -> frozenset[str]:
        return self.ALLOWED_TOOL_NAMES

    def get_A_PurchaseOrder(self, PurchaseOrder: str) -> APurchaseOrder:
        self._record("get_A_PurchaseOrder", PurchaseOrder=PurchaseOrder)
        return self._get_one(
            APurchaseOrder,
            f"A_PurchaseOrder({_literal(PurchaseOrder)})",
            f"purchase order {PurchaseOrder!r} not found",
        )

    def get_A_PurchaseOrderItem(
        self, PurchaseOrder: str, PurchaseOrderItem: str
    ) -> APurchaseOrderItem:
        self._record(
            "get_A_PurchaseOrderItem",
            PurchaseOrder=PurchaseOrder,
            PurchaseOrderItem=PurchaseOrderItem,
        )
        return self._get_one(
            APurchaseOrderItem,
            f"A_PurchaseOrderItem(PurchaseOrder={_literal(PurchaseOrder)},"
            f"PurchaseOrderItem={_literal(PurchaseOrderItem)})",
            f"purchase order item {PurchaseOrder!r}/{PurchaseOrderItem!r} not found",
        )

    def list_A_MaterialDocumentItem(
        self, PurchaseOrder: str, PurchaseOrderItem: str
    ) -> tuple[AMaterialDocumentEntry, ...]:
        self._record(
            "list_A_MaterialDocumentItem",
            PurchaseOrder=PurchaseOrder,
            PurchaseOrderItem=PurchaseOrderItem,
        )
        return self._list(
            AMaterialDocumentEntry,
            "A_MaterialDocumentItem",
            PurchaseOrder,
            PurchaseOrderItem,
            orderby="PostingDate,MaterialDocument,MaterialDocumentItem",
        )

    def list_A_SupplierInvoiceItemPurOrdRef(
        self, PurchaseOrder: str, PurchaseOrderItem: str
    ) -> tuple[ASupplierInvoiceEntry, ...]:
        self._record(
            "list_A_SupplierInvoiceItemPurOrdRef",
            PurchaseOrder=PurchaseOrder,
            PurchaseOrderItem=PurchaseOrderItem,
        )
        return self._list(
            ASupplierInvoiceEntry,
            "A_SupplierInvoiceItemPurOrdRef",
            PurchaseOrder,
            PurchaseOrderItem,
            orderby="PostingDate,SupplierInvoice,SupplierInvoiceItem",
        )

    def _get_one[M: BaseModel](self, model: type[M], path: str, not_found: str) -> M:
        response = self._client.get(f"{self._url(path)}?{_query({'$select': _select(model)})}")
        if response.status_code == 404:
            raise FixtureLookupError(not_found)
        response.raise_for_status()
        return _parse(model, response.json())

    def _list[M: BaseModel](
        self,
        model: type[M],
        entity_set: str,
        purchase_order: str,
        purchase_order_item: str,
        *,
        orderby: str,
    ) -> tuple[M, ...]:
        query = _query(
            {
                "$filter": (
                    f"PurchaseOrder eq {_literal(purchase_order)} and "
                    f"PurchaseOrderItem eq {_literal(purchase_order_item)}"
                ),
                "$orderby": orderby,
                "$select": _select(model),
            }
        )
        url: str | None = f"{self._base}/{entity_set}?{query}"
        rows: list[M] = []
        while url is not None:
            response = self._client.get(url)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict) or not isinstance(body.get("value"), list):
                raise ValueError("Invalid OData collection: expected a value array")
            if not all(isinstance(row, dict) for row in body["value"]):
                raise ValueError("Invalid OData collection: expected object rows")
            rows.extend(_parse(model, row) for row in body["value"])
            next_link = body.get("@odata.nextLink")
            # A next link carries its own query string; resolve it against
            # the service root and send it as given.
            url = str(httpx.URL(f"{self._base}/").join(next_link)) if next_link else None
        if not rows:
            self._confirm_item_exists(purchase_order, purchase_order_item)
        return tuple(rows)

    def _confirm_item_exists(self, purchase_order: str, purchase_order_item: str) -> None:
        """Frozen mode raises for an unknown item on every lookup, including
        the lists. An empty list from a filter cannot tell "no documents" from
        "no such item", so ask once."""
        path = (
            f"A_PurchaseOrderItem(PurchaseOrder={_literal(purchase_order)},"
            f"PurchaseOrderItem={_literal(purchase_order_item)})"
        )
        response = self._client.get(f"{self._url(path)}?{_query({'$select': 'PurchaseOrder'})}")
        if response.status_code == 404:
            raise FixtureLookupError(
                f"purchase order item {purchase_order!r}/{purchase_order_item!r} not found"
            )
        response.raise_for_status()

    def _url(self, path: str) -> str:
        # Keep the key-predicate characters literal; percent-encode the rest.
        return f"{self._base}/{quote(path, safe=_KEY_PREDICATE_CHARS)}"

    def _record(self, name: str, **arguments: str) -> None:
        if name not in self.ALLOWED_TOOL_NAMES:
            raise ToolAccessDenied(f"tool {name!r} is not allowlisted for read-only access")
        self._tool_calls.append(ToolCall(name=name, arguments=dict(arguments)))


def _parse[M: BaseModel](model: type[M], row: dict[str, Any]) -> M:
    """Build `model` from one OData row: drop annotations such as
    `@odata.etag`, and fold flattened columns (`CreatedByUser_user_id`) back
    into their nested model. An already-nested value is accepted as is."""
    data = {k: v for k, v in row.items() if not k.startswith("@")}
    for name, field in model.model_fields.items():
        nested = _nested_model(field.annotation)
        if nested is None or name in data:
            continue
        data[name] = {sub: data.pop(f"{name}_{sub}") for sub in nested.model_fields}
    return model.model_validate(data)
