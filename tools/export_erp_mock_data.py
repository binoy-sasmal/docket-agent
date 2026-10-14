"""Generate the CAP mock ERP's seed data from the frozen fixtures.

Writes one CSV per entity into erp-mock/db/data/, which CAP loads into its
in-memory database at startup. The CSVs are generated, never committed or
edited: the frozen fixtures stay the single source of truth, so the mock
cannot drift from what the eval measures.

Exports exactly what `ReadOnlyODataTools` serves -- the frozen selection,
without injection overlays -- and refuses to write anything if two cases
disagree about a shared document (a purchase order header shared by two
items, say), or if a timestamp is not UTC.

Usage:
    python tools/export_erp_mock_data.py
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from docket.fixture_store import FrozenFixtureStore
from docket.schema.procurement import ActingUser

OUT_DIR = Path(__file__).resolve().parents[1] / "erp-mock" / "db" / "data"
NAMESPACE = "docket.erp"

# Known fixture artefact, found by this script on 2026-10-14: the two items
# of purchase order 4508076337 (cases _00040 and _00140, neither in the golden
# set) carry header dates 20 minutes apart in their rendered files,
# apparently each item's creation time. An ERP has one header per order. The
# mock keeps the first selected case's header, which is exactly what
# ReadOnlyODataTools.get_A_PurchaseOrder already returns for both items, so
# connected and frozen mode serve the same header. Only this order and only
# this field are resolved; any other disagreement still stops the export.
# The fixtures are frozen and are not edited here.
RESOLVED_HEADER_DATE_CONFLICTS = frozenset({"4508076337"})


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        if value.utcoffset() != timedelta(0):
            raise ValueError(f"non-UTC timestamp {value.isoformat()} cannot round-trip as Z")
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "value"):  # enums such as Provenance
        return str(value.value)
    return str(value)


def _flatten(model: BaseModel) -> dict[str, str]:
    """One CSV row. A structured element (CreatedByUser) becomes
    CreatedByUser_user_id / CreatedByUser_is_batch_user, CAP's CSV naming."""
    row: dict[str, str] = {}
    for name in type(model).model_fields:
        value = getattr(model, name)
        if isinstance(value, ActingUser):
            for sub in ActingUser.model_fields:
                row[f"{name}_{sub}"] = _cell(getattr(value, sub))
        else:
            row[name] = _cell(value)
    return row


def main() -> None:
    store = FrozenFixtureStore()
    tables: dict[str, dict[tuple[str, ...], dict[str, str]]] = {
        "PurchaseOrders": {},
        "PurchaseOrderItems": {},
        "MaterialDocumentItems": {},
        "SupplierInvoiceItems": {},
    }
    conflicts: list[str] = []

    def put(table: str, key: tuple[str, ...], model: BaseModel) -> None:
        row = _flatten(model)
        existing = tables[table].setdefault(key, row)
        if existing == row:
            return
        differing = {name for name in row if row[name] != existing[name]}
        if (
            table == "PurchaseOrders"
            and key[0] in RESOLVED_HEADER_DATE_CONFLICTS
            and differing == {"PurchaseOrderDate"}
        ):
            return  # keep the first selected case's header, as the frozen tools do
        conflicts.append(f"{table} {key}: {sorted(differing)}")

    for case_id in store.selected_case_ids:
        doc = store.load_case(case_id)
        po, item = doc.purchase_order, doc.purchase_order_item
        put("PurchaseOrders", (po.PurchaseOrder,), po)
        put("PurchaseOrderItems", (item.PurchaseOrder, item.PurchaseOrderItem), item)
        for gr in doc.goods_receipts:
            key = (gr.MaterialDocumentYear, gr.MaterialDocument, gr.MaterialDocumentItem)
            put("MaterialDocumentItems", key, gr)
        for inv in doc.invoices:
            key = (inv.SupplierInvoice, inv.FiscalYear, inv.SupplierInvoiceItem)
            put("SupplierInvoiceItems", key, inv)

    if conflicts:
        sys.exit(
            "refusing to export; cases disagree about shared documents:\n" + "\n".join(conflicts)
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for table, rows in tables.items():
        path = OUT_DIR / f"{NAMESPACE}-{table}.csv"
        ordered = [rows[key] for key in sorted(rows)]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(ordered[0]))
            writer.writeheader()
            writer.writerows(ordered)
        print(f"{path.name}: {len(ordered)} rows")


if __name__ == "__main__":
    main()
