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
- Note hypotheses: a model extracts at most one claim of four fixed kinds from untrusted note
  text, code checks it against the documents, and the approver sees a fixed UNVERIFIED template.
  Labels frozen before the feature existed.
- AgentOps: content-free run tracing (nodes, model calls, tokens, tool calls, errors), an
  operations report, a case-by-case release gate between two runs, and a single-case replay.

## Evidence map

| Claim area | Verify here |
|---|---|
| Current implementation and measured results | `README.md` sections Status and Known limits |
| Architecture and permission boundaries | `docs/PROJECT.md` section 3 and `tests/test_architecture.py` |
| Dataset derivation and authored fields | `docs/DERIVATION.md` |
| Human-approval behavior | `tests/test_approval_memory.py` |
| Note hypotheses: design, frozen labels, live result and caveats | `README.md` "Note hypotheses"; `src/docket/hypothesis.py`; `evals/notes/` (labels, FROZEN.md, manifest); `tools/run_note_eval.py`; `tests/test_note_hypothesis.py`; `evals/draft/held_out_note_brief.md` |
| Connected mode and the CAP mock ERP | `README.md` "Connected mode"; `erp-mock/` (CDS model and service, README); `src/docket/tools/odata_http.py`; `tests/test_erp_mock_equivalence.py`; `tests/test_odata_http.py`; `.github/workflows/ci.yml` job `erp-mock` |
| Durable approval: restart safety, idempotency, audit trail | `README.md` "Durable approval"; `src/docket/durable.py`; `src/docket/approval.py`; `tests/test_durable_workflow.py`; the web UI's restart test `tests/test_ui_durable.py` (needs the `ui` extra, so it is skipped in CI) |
| AgentOps: tracing, report, release gate, replay | `README.md` "Operations (AgentOps)"; `src/docket/ops.py`; `tests/test_ops.py`; `tools/ops_report.py`; `tools/compare_runs.py`; `tools/replay_case.py`; `--ops-out` in `tools/run_eval.py` |
| Golden-set provenance | `evals/golden/FROZEN.md` |
| UI scope and limitations | `ui/README.md` |

## Safe application framing

- Describe this as a portfolio agent for investigating ERP invoice exceptions.
- State that the agent proposes but cannot post.
- Describe SAP entities as OData-shaped fixtures, not a live SAP integration.
- Note hypotheses: "the agent extracts a constrained claim from untrusted notes and code checks
  it; on 13 public cases written before the feature, the live model got every claim right and
  never changed a decision or leaked a coercive phrase". Always add that the public cases share
  an author with the feature and the run is a single pass; quote held-out results separately
  once they exist.
- Connected mode: "built a read-only SAP CAP OData v4 service and an HTTP tool adapter, and proved
  the agent decides identically on all 300 cases in both modes". The service is a mock seeded from
  the fixtures.
- Pair every evaluation result with its denominator and the limitations in `README.md`.
- Live run (2026-11-01/02, 38 case-runs, `README.md` Status and "Prompt-cache experiment"):
  dispositions and trajectories 100% correct (30/30); 0/8 injections succeeded, including 0/4
  held out; measured with content-free tracing (median 27.5 s per case-run, 21.6% of input tokens
  from the prompt cache). Always pair the result with its denominator: 8 attacks, 4 held out, one
  run, and the held-out payloads' second complete evaluation (two of them also ran in an
  interrupted cap-1,500 attempt and in partial run B, none successfully; README Status).
- AgentOps: "added content-free tracing of every node, model call and tool call, an operations
  report, and a release gate that compares two runs case by case and fails on outcome, token,
  latency or step-budget regressions". Tested offline, run end to end in deterministic mode, and
  used on one live run (above).
  Never use the bare term: name its components (run tracing, ops report with cost and latency,
  release gate, run replay, prompt-cache tracking) so an interviewer knows what was built.
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
- A cache saving from the `shared_prefix` layout: measured on 17 case-runs, it lowered prompt-cache
  hits (28.0% to 11.8%), so the default layout stays.
- Cost figures: the live run used the free tier and no prices were applied. A completed
  model-version comparison: none has been made. OpenTelemetry export, dashboards or production
  monitoring for Docket: the ops data is local JSONL.
- Note-hypothesis results as independent or as a robustness rate: one run, public cases by the
  feature's author, held-out cases not yet authored.
- That approvers never see note text: the UI shows raw notes in a labelled untrusted panel by
  design. The guarantee covers agent-generated text only.
- Integration with a real SAP system, S/4HANA, or SAP BTP. The CAP service is a local mock, not
  deployed, and has no authentication because it serves only fixture data.
- CAP experience beyond a read-only CDS model and service: no custom handlers, actions,
  authorisation, or deployment.

## Verification rule

Before using a metric or implementation-status claim, verify it against the current `README.md` and the referenced artifact. Record the repository commit in the application analysis; do not treat a commit recorded in this file as permanently current.
