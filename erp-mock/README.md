# erp-mock

A read-only SAP CAP service exposing the four OData entity sets Docket's
Investigator reads, seeded from the frozen fixtures. It exists so Docket can
run in **connected mode** -- the same graph reading documents over HTTP from
an OData v4 service instead of from local files -- and so that mode can be
tested against frozen mode case by case.

It is a test service, not an ERP, and not a connection to any SAP system.

| Entity set | Key | Docket model |
|---|---|---|
| `A_PurchaseOrder` | `PurchaseOrder` | `APurchaseOrder` |
| `A_PurchaseOrderItem` | `PurchaseOrder`, `PurchaseOrderItem` | `APurchaseOrderItem` |
| `A_MaterialDocumentItem` | `MaterialDocumentYear`, `MaterialDocument`, `MaterialDocumentItem` | `AMaterialDocumentEntry` |
| `A_SupplierInvoiceItemPurOrdRef` | `SupplierInvoice`, `FiscalYear`, `SupplierInvoiceItem` | `ASupplierInvoiceEntry` |

## Run it

Needs Node 22 or newer.

```
python tools/export_erp_mock_data.py        # seed data, from the frozen fixtures
cd erp-mock && npm ci && npm start          # http://localhost:4004/odata/v4/procurement
```

Then, from the repository root:

```
DOCKET_ERP_URL=http://localhost:4004/odata/v4/procurement pytest -m erp
```

To run the graph against it, pass
`tools_factory=lambda: HttpODataTools(url)` to `build_docket_graph`
(`docket.tools.odata_http`). Frozen mode stays the default, and injection
overlays cannot be combined with connected mode: they are an eval
instrument, and a run that depends on a server is never an eval run.

## What is checked

`tests/test_erp_mock_equivalence.py`, run by CI in its own job:

- the service serves all 300 frozen-selected cases;
- every lookup returns the same documents as frozen mode, for all 300;
- the deterministic pipeline makes the same tool calls, the same policy
  decision and the same proposal for all 300, with identical claim text;
- `POST`, `PATCH` and `DELETE` are refused with 405, and the data is unchanged.

The one tolerated difference is document **order**. An ERP returns documents
in query order (posting date, then key); the fixtures do not follow that order
for every case. A claim lists the documents it cites in arrival order, so
evidence is compared as a set. Re-sorting the fixtures the same way leaves all
30 golden dispositions and trajectories unchanged.

## Design notes

- **Seed data is generated, never committed.** `db/data/` is gitignored, so the
  mock cannot drift from the fixtures the eval measures. The export refuses
  to run if two cases disagree about a shared document.
- **One known fixture artefact.** The two items of purchase order `4508076337`
  carry header dates 20 minutes apart in their rendered files. An ERP has one
  header per order; the mock keeps the first selected case's header, which is
  what the frozen tools already return for both items. Neither case is in the
  golden set, and no decision logic reads the date. The fixtures were not
  changed.
- **Decimal scale mirrors the fixtures** (net price one decimal place, document
  amounts two). Docket's claim text prints an amount at the scale its source
  supplies, so a real ERP sending `243.00` where the fixtures hold `243.0`
  would change a proposal's wording, though not its decision. Recorded in the
  main README's known limits.
- **The acting user is flattened** (`CreatedByUser_user_id`,
  `CreatedByUser_is_batch_user`), CAP's default OData shape for a structured
  type. The adapter folds the columns back into Docket's nested model. Real
  SAP APIs carry `CreatedByUser` as a plain string; the nested user is
  Docket's own modelling.
- **Decimals travel as strings.** The adapter asks for
  `IEEE754Compatible=true`, so no amount passes through a binary float.

## Licence

`@sap/cds` is distributed under the SAP Developer License Agreement (3.2 CAP),
which permits applications built for testing and non-productive use. This is
a test service and is used only that way. `@cap-js/sqlite` is Apache-2.0.
