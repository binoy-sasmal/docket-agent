# Application Evidence: Docket

This is a routing document for job-application work. It does not replace the project documentation.

## Status

Complete portfolio system. The authoritative status, measured results, caveats, and reproducibility instructions are in `README.md`.

## What it demonstrates

- LangGraph agent design with node-specific tool permissions.
- Human approval through `interrupt()` before the only mutable action.
- Deterministic policy enforcement outside the model.
- Evidence-grounded output and prompt-injection evaluation.
- Frozen fixtures, contamination controls, and CI evaluation gates.
- Durable, restart-safe approval: a paused case resumed by a different process, an exactly-once
  approved write under replay, and an append-only audit trail enforced by the database.
- Connected mode: the same agent reading over HTTP from a read-only SAP CAP OData v4 service,
  proven equivalent to frozen mode on all 300 cases in a dedicated CI job.

## Evidence map

| Claim area | Verify here |
|---|---|
| Current implementation and measured results | `README.md` sections Status and Known limits |
| Architecture and permission boundaries | `docs/PROJECT.md` section 3 and `tests/test_architecture.py` |
| Dataset derivation and authored fields | `docs/DERIVATION.md` |
| Human-approval behavior | `tests/test_approval_memory.py` |
| Connected mode and the CAP mock ERP | `README.md` "Connected mode"; `erp-mock/` (CDS model and service, README); `src/docket/tools/odata_http.py`; `tests/test_erp_mock_equivalence.py`; `tests/test_odata_http.py`; `.github/workflows/ci.yml` job `erp-mock` |
| Durable approval: restart safety, idempotency, audit trail | `README.md` "Durable approval"; `src/docket/durable.py`; `src/docket/approval.py`; `tests/test_durable_workflow.py`; the web UI's restart test `tests/test_ui_durable.py` (needs the `ui` extra, so it is skipped in CI) |
| Golden-set provenance | `evals/golden/FROZEN.md` |
| UI scope and limitations | `ui/README.md` |

## Safe application framing

- Describe this as a portfolio agent for investigating ERP invoice exceptions.
- State that the agent proposes but cannot post.
- Describe SAP entities as OData-shaped fixtures, not a live SAP integration.
- Connected mode: "built a read-only SAP CAP OData v4 service and an HTTP tool adapter, and proved
  the agent decides identically on all 300 cases in both modes". The service is a mock seeded from
  the fixtures.
- Pair every evaluation result with its denominator and the limitations in `README.md`.
- Durable approval: "restart-safe, exactly-once human approval with an append-only audit trail,
  proven across separate processes", in the library and in the web UI. SQLite, single node, one
  UI worker.

## Unsupported claims

- Production deployment or customer usage.
- Connection to a live ERP or SAP system.
- Accounts-payable consulting expertise.
- Broad prompt-injection robustness beyond the documented evaluation set.
- Distributed or multi-node durability, concurrent approvers across machines, or Postgres-backed
  persistence.
- Event streaming or Kafka; none exists in this system.
- Integration with a real SAP system, S/4HANA, or SAP BTP. The CAP service is a local mock, not
  deployed, and has no authentication because it serves only fixture data.
- CAP experience beyond a read-only CDS model and service: no custom handlers, actions,
  authorisation, or deployment.

## Verification rule

Before using a metric or implementation-status claim, verify it against the current `README.md` and the referenced artifact. Record the repository commit in the application analysis; do not treat a commit recorded in this file as permanently current.
