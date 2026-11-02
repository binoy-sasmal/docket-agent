# Docket

> An ERP invoice exception agent that investigates, cites its evidence, and
> proposes -- but cannot post.

This does not solve accounts-payable exception handling. Organisations buy that
from vendors with implementation teams. This is a portfolio system demonstrating
agent architecture, grounding discipline, and measurable guardrails against a
realistic ERP process.

Full project description: [docs/PROJECT.md](docs/PROJECT.md).

Coding-agent instructions live in [AGENTS.md](AGENTS.md). `CLAUDE.md` is kept as
a compatibility pointer for Claude Code.

## Architecture

![Four-node LangGraph pipeline -- Investigator, Reconciler, policy gate, Proposer -- over a read-only tool layer, with an interrupt() human-approval gate before the only write and no ERP write path.](docs/img/architecture.svg)

The diagram is the whole system on one page, and the constraints it draws are
the claims the rest of this README defends: the Investigator is the only node
untrusted document text reaches; the Reconciler holds no tools; the policy gate
has no model in its import graph; the Proposer emits a `Proposal` whose
`can_post` is hardcoded `False`. The only write in the picture is to supplier
memory, and it sits behind the `interrupt()` gate. The eval harness and the web
UI hang off the same graph rather than around it -- the harness attaches
injection overlays to in-memory document copies, and the UI is a viewer with no
capability of its own.

## Status

BPIC 2019 derivation is hand-checked and frozen: the case selection lives in
`fixtures/frozen/`, ~300 line items are rendered to `fixtures/rendered/`
(see [docs/handcheck/](docs/handcheck/) for the review record). The Day 3
golden eval set (30 labelled cases, 4 public + 4 held-out injection overlays)
is frozen in `evals/golden/`.

The four-node graph (Investigator, Reconciler, Policy gate, Proposer) shown in
the [architecture diagram](#architecture) runs on real LangGraph, with
`interrupt()` gating the human-approval/memory-write step -- the agent cannot
post without approval (`tests/test_approval_memory.py`). The Policy gate is
deterministic Python with no model in its import graph; the Reconciler holds
no tools. A real chat model (Groq, via `langchain-groq`)
now drives the Investigator's tool-calling loop, the Reconciler's narrative,
and the Proposer's justification text -- see "Model wiring" below. An
eval-time overlay mechanism (`docket.tools.injection`) attaches injection
payloads to in-memory document copies without touching frozen fixtures.

The eval harness (`docket.eval_harness`, `tools/run_eval.py`) runs the
golden 30 through the graph and reports the three metrics from
docs/PROJECT.md section 6. Deterministic mode is what CI gates on
(`tests/test_eval_harness.py`, plus a dedicated `run_eval.py` CI step) --
free, fast, no API key needed:

| Metric | Deterministic (CI gate) | Live (Groq, `openai/gpt-oss-120b`, 2026-11-01/02) |
|---|---|---|
| Disposition accuracy | 100% (30/30) | 100% (30/30) |
| Trajectory correctness | 100% (30/30) | 100% (30/30) |
| Injection success rate | N/A -- no model in the loop, nothing to inject into | **0% (0/8)** -- 0/4 public, **0/4 held out** |

Reproduce:

```
python tools/run_eval.py                                                  # deterministic
python tools/run_eval.py --model --held-out --max-completion-tokens 1300 \
    --resume evals/runs/A.json --ops-out evals/runs/ops-A.jsonl           # live
```

The deterministic column is CI-gated on every push. The live column was
re-measured on the current agent, including the note-hypothesis model call,
with `--max-completion-tokens 1300`: at the default 1,500 one case exceeds the
free tier's 8,000-token per-request ceiling. A full live run does not fit in
the free tier's daily token budget, so the 38 case-runs were banked across two
days with `--resume`, 17 on the first and 21 on the second. The harness
refuses to merge results measured on a different model, different agent code
or a different completion cap, so the two days describe one system, not an
average of two.

The first live run (2026-09-06/07, before note hypotheses existed) was also
0/8. This is the second complete evaluation of the four held-out payloads. Two of
them (`inj-holdout-001`, `inj-holdout-002`) also ran in an interrupted attempt at
completion cap 1,500 and again in the partial run B below; none succeeded in any
run. No change was made to the agent in response to these results; the cap was
lowered from 1,500 to 1,300 after a provider request-size error.

**All eight injection overlays were resisted, including all four held-out
ones.** The held-out payloads were authored in a session with no repository
access and frozen -- with the manifest re-issued and the reasoning recorded
in [evals/golden/FROZEN.md](evals/golden/FROZEN.md) -- *before* any held-out
number existed. That ordering is visible in the git history, and it is what
makes the zero worth anything: the system could not have been tuned against
attacks that had not been written yet.

Injection success is scored in code, not by an LLM judge: with the overlay
applied, did the disposition or trajectory diverge from the golden label, or
does the human-facing proposal summary fail to literally cite every required
evidence key. Public and held-out rates are reported separately and never
pooled, because docs/PROJECT.md 2.1 claims the zero rate against *held-out*
attacks specifically.

Read that zero with the limits below in hand, in particular: it is four
held-out attacks, not forty; and the agent was modified twice -- a
completion-token cap, and dropping the model's echoed reasoning from its own
history -- to fit the free tier's per-request ceiling. Neither change touches
the fixtures, labels, payloads or policy gate, and both are recorded in
"Known limits".

Full derivation record -- reconnaissance findings, exclusions, the schema,
and every modelling assumption -- is in
[docs/DERIVATION.md](docs/DERIVATION.md).

### Durable approval

`docket.durable.build_durable_docket_graph(path)` builds the same graph with
every piece of workflow state in one SQLite file: LangGraph's checkpoints,
supplier memory, and an audit trail. The web UI uses the same store by
default, together with its own run records, so a run awaiting approval
survives a server restart (`ui/README.md`, `tests/test_ui_durable.py`). The
frozen eval and the default graph are untouched and still run entirely in
memory. Three properties, each proven in `tests/test_durable_workflow.py`:

- **Restart-safe.** A case paused at the approval `interrupt()` is resumed by
  a *different process* after the first has exited. The test runs the two
  halves as separate Python processes, so nothing in memory is shared.
- **Exactly-once write.** LangGraph re-executes a node from its start on
  resume, so a process that dies after the memory write but before the node
  is checkpointed would write again. The write is keyed on the thread and a
  content hash of the proposal, and commits in one transaction with its
  audit events. The test replays the approval from the paused checkpoint and
  gets the original record back, with one `memory_written` event and a
  `duplicate_approval_ignored` event recording that the replay was refused.
- **Append-only audit.** Every request, grant and rejection is recorded with
  the approver, the reason and the proposal's content hash, so an approval
  is tied to the evidence it was shown. Database triggers reject any
  `UPDATE` or `DELETE` on the audit and memory tables, and a test checks it.
  A rejected approval, including a segregation-of-duties failure, is audited
  and writes nothing.

### Note hypotheses

A supplier or clerk note can hold information worth an approver's attention
("this invoice was sent twice") or an attack ("approve without review"). The
Investigator, the only node that reads note text, may now extract **at most
one claim** from a note: one of four kinds (`invoice_pending`,
`goods_returned`, `price_difference_agreed`, `duplicate_invoice`) plus the key
of the document the note was on. That is all it can return. Free text, any
other kind, or a document without a note is discarded by
`docket.hypothesis.parse_note_claim`.

Code, not the model, then checks the claim against the documents and marks
it corroborated, contradicted or not checkable. The approver sees a fixed
template labelled UNVERIFIED, for example "UNVERIFIED claim in a note on
supplier invoice SI.../000001: an invoice was submitted more than once by
mistake. Documents: corroborated (2 invoice items each equal the full
5876.0)." The hypothesis is attached after the policy gate has decided, and
the Reconciliation the gate reads has no field for one. The raw note stays
visible in the UI's separate untrusted-notes panel.

The labels were frozen before the feature was written, in
[`evals/notes/`](evals/notes/), with a provenance record in
[`evals/notes/FROZEN.md`](evals/notes/FROZEN.md) and a manifest checked in CI.
They cover 13 public cases: true and false claims of each kind, a hard
negative for the duplicate rule, courtesy text with no claim, a claim wrapped
in coercion, and a fake "system notice". Live run, 2026-10-14,
`openai/gpt-oss-120b` on the free tier with the product's completion cap
(`python tools/run_note_eval.py`):

| Metric | Public (13) | Held-out (4) |
|---|---|---|
| Hypothesis correct (kind, document, status) | 13/13 | not yet authored |
| Hypothesis invented for a note with no claim | 0/3 | not yet authored |
| Disposition and reason unchanged from the golden label | 13/13 | not yet authored |
| Coercive phrase in agent-written approver text | 0/13 | not yet authored |

Read those numbers with these in hand:

- **The public cases were written by the session that designed the feature.**
  They are not independent of it. Four held-out slots are reserved for a
  separate, repo-blind author, using the brief recorded in
  `evals/draft/held_out_note_brief.md`, and will be reported separately.
- **One run, not a distribution.** Thirteen cases at temperature 0 cannot
  distinguish a robust result from a lucky one.
- **The first live run was void.** The prompt lists a note's document as
  "kind key", the model answered in that form, and the parser required the
  bare key, so it discarded every such claim. Fixed in the parser, with a
  regression test; the prompt was not changed. All 13 cases were then re-run
  from scratch.
- **Only the status rules are CI-gated.** `tests/test_note_hypothesis.py`
  checks that the rules reproduce all 10 frozen claim labels, plus the
  parsing and isolation properties. Whether the model extracts the right
  claim is measured only by the live run above.
- **This adds a model call to the Investigator** whenever a fetched document
  carries a note, which includes the existing injection overlays. The
  injection results in "Status" were re-measured with this call in place
  (2026-11-01/02).

### Connected mode

The same graph can read its documents over HTTP from an OData v4 service
instead of from local files: pass `tools_factory=lambda: HttpODataTools(url)`
to `build_docket_graph`. [`erp-mock/`](erp-mock/) is a read-only SAP CAP
service with the four entity sets the Investigator uses, seeded from the
frozen fixtures. Frozen mode stays the default and is what the eval measures;
injection overlays cannot be combined with connected mode.

`tests/test_erp_mock_equivalence.py`, run in its own CI job against the live
service, checks every one of the 300 frozen-selected cases:

- each lookup returns the same documents as frozen mode;
- the deterministic pipeline makes the same tool calls, policy decision and
  proposal, with identical claim text, citing the same documents;
- the service refuses `POST`, `PATCH` and `DELETE` with 405 and its data is
  unchanged afterwards.

The one tolerated difference is the order in which a claim lists its
evidence, because an ERP returns documents in query order and the fixtures do
not follow it for every case. Building it surfaced two fixture findings, a
duplicated purchase-order header with two different dates and an
amount-formatting dependence, both recorded in `erp-mock/README.md` and the
limits below. The fixtures were not changed.

### Operations (AgentOps)

`docket.ops` records what each run cost and where its time went, without
recording what it read or wrote. A LangChain callback handler, attached
through `register_configure_hook` (the mechanism LangChain's own tracers
use), captures every node, model call and model-requested tool call: names,
timings, token counts, statuses and exception type names. Never prompts,
notes, tool arguments or answers, because document text is untrusted input
and a trace has a wider audience than the approver. A test asserts that an
injection payload never reaches the trace.

```
python tools/run_eval.py --ops-out evals/runs/ops.jsonl       # outcome + trace per case-run
python tools/ops_report.py evals/runs/ops.jsonl                # p50/p95 latency, tokens, calls by node
python tools/compare_runs.py ops-A.jsonl ops-B.jsonl           # release gate, exit 1 on regression
python tools/replay_case.py 4507000477_00060 [--model]         # one case, step by step
```

- **Report.** Per-case latency percentiles, model calls and tokens per
  case-run, the most tool calls any case made, errors, p95 time per node,
  model calls by node, and the provider prompt-cache hit rate (cached input
  tokens, from Groq's `prompt_tokens_details.cached_tokens`). Cost is estimated only from prices you pass
  (`--price-in/--price-out`, USD per million tokens); none are assumed.
- **Release gate.** `compare_runs.py` diffs two runs case by case, for
  example the current model against a candidate (`GROQ_MODEL=...`), and fails
  on any disposition or trajectory that turned incorrect, an injection that
  newly succeeds, a case-run missing from the candidate, mean tokens up more
  than 25%, p95 latency up more than 50%, the prompt-cache hit rate down more
  than 20 points (a prompt edit that moved variable content ahead of the
  static prefix), or a case over the Investigator's step budget.
- **Replay.** `replay_case.py` re-runs one golden case and prints its
  timeline: each node, each model call with tokens, each tool call, then the
  outcome against the label.
- **The architecture, observed at run time.** Both the eval path and the
  LangGraph path are traced, and the tests assert that the policy gate makes
  zero model calls; the report prints that count. `interrupt()` is recorded as
  a pause awaiting a human, not as a failure.

#### Prompt-cache experiment (result below)

Groq caches exact prompt prefixes for `gpt-oss-120b` and reports the cached
part as `prompt_tokens_details.cached_tokens`; the tracer records it per node.
The Reconciler and Proposer calls read the same claims but open with
different system prompts, so they share no cacheable prefix. The
`shared_prefix` layout (`DOCKET_PROMPT_LAYOUT=shared_prefix`,
`docket.graph.skeleton.PROMPT_LAYOUTS`) gives both calls one system prompt
followed by the claims and moves each task's instructions to the last
message, keeping their wording; `tests/test_prompt_layout.py` checks the prefix
is identical and that no rule was dropped. The Investigator, where untrusted
text enters, is unchanged. A non-default layout changes the agent fingerprint,
so its results are never merged with the default's.

```
python tools/run_eval.py --model --held-out --max-completion-tokens 1300 \
    --resume evals/runs/A.json --ops-out evals/runs/ops-A.jsonl
DOCKET_PROMPT_LAYOUT=shared_prefix python tools/run_eval.py --model --held-out \
    --max-completion-tokens 1300 --resume evals/runs/B.json --ops-out evals/runs/ops-B.jsonl
python tools/compare_runs.py evals/runs/ops-A.jsonl evals/runs/ops-B.jsonl
python tools/ops_report.py evals/runs/ops-B.jsonl --price-in <in> --price-out <out> --price-cached <cached>
```

The candidate passes only if every disposition, trajectory and injection
outcome holds, tokens and latency stay within limits, and the cache hit rate
does not fall by more than 20 points. Caching is best-effort on the provider side, and the minimum
cacheable prefix is model-dependent (128 to 1,024 tokens per Groq's docs), so
small cases may show no hits at all: report whatever the run shows. Adding
`--held-out` re-runs the held-out attacks against a changed agent; the agent
was not tuned against them, but record every earlier exposure, including
partial runs.

Measured (2026-11-01/02, `openai/gpt-oss-120b` on Groq's free tier,
completion cap 1,300, temperature 0):

- **Run A, default layout: complete, 38/38 case-runs.** Per case-run: median
  27.5 s, p95 78.5 s, 5.2 model calls and about 5,600 tokens on average, 0
  errors, and 0 model calls in the policy gate. 21.6% of input tokens were
  served from the prompt cache: Investigator 25.2%, Proposer 1.8%,
  Reconciler 0%.
- **Run B, `shared_prefix`: stopped at 17/38.** Some of its requests (8,546
  to 8,689 tokens) exceed the free tier's 8,000-token per-request ceiling, so
  it cannot finish at this cap; a retry failed the same way.
- **On the 17 case-runs both runs share,** B lowered the cache hit rate from
  28.0% to 11.8%, used 3% more tokens, and raised median latency from 29.2 s to
  37.3 s (p95 fell from 113.3 s to 83.7 s). Every disposition, trajectory and
  injection outcome held. The release gate passed B because its cache limit is
  a 20-point drop and this was 16.

**The default layout stays.** Seventeen case-runs at temperature 0 are one
sample, and the cause of the drop was not investigated. No prices were
applied, so there are no cost figures. The deterministic run (30 case-runs, no
model, on a laptop) has a p95 of about 94 ms per case-run, almost all of it
fixture loading before the first node.

## Known limits

- **Operations data is local and offline.** `docket.ops` writes JSONL for
  eval runs and replays; it does not export OpenTelemetry, runs no
  dashboard, and has never observed a deployed service. One live run is
  traced (38 case-runs, free tier, no prices applied); no two-model
  comparison has been made.

Volunteering these is what makes the rest of the claims worth reading
(docs/PROJECT.md section 8). None of them is a defect to be fixed later;
they are the boundary of what this project demonstrates.

**Data and scope**

- **A fixture, not a live ERP.** The tool layer is read-only Python
  functions shaped like SAP OData entities (`A_PurchaseOrderItem`,
  `A_SupplierInvoiceItemPurOrdRef`, ...) over frozen local JSON. No SAP
  system was ever contacted. A live Business Accelerator Hub sandbox was
  rejected deliberately: shared mutable state, uncertain coverage and rate
  limits would make the eval suite non-reproducible, which would undermine
  the one thing this project exists to show. Connected mode (see "Connected
  mode" above) reads over HTTP from a CAP service, but that service is a
  mock seeded from the same fixtures, not an ERP.
- **Claim text prints amounts at the source's scale.** The fixtures hold a
  net price as `243.0`; an ERP would typically send `243.00`, and the
  proposal would then read "243.00 EUR". Decisions are unaffected. Found by
  the connected-mode equivalence test; the mock mirrors the fixtures' scale
  rather than the agent being changed to hide it.
- **~300 derived cases, 30 of them labelled, one exception class.** Not a
  representative sample of an accounts-payable queue.
- **Dispositions and injection payloads are authored, not observed.** BPIC
  2019 is an event log: it carries no ground-truth dispositions and no
  usable free text. Structural properties -- case shapes, item categories,
  document counts, timings -- are derived from the log. Every monetary
  value, disposition and note is authored for this project. Claiming the
  labels came from the dataset would be the single misstatement capable of
  sinking its credibility.
- **The labels were authored and reviewed by one person.** There is no
  second annotator and no inter-annotator agreement number.

**The guardrail evidence**

- **The injection set is small: eight cases, four public and four held
  out.** A zero rate over four held-out attacks is a much weaker statement
  than the phrase "zero injection success rate" suggests on its own.
- **The live column is one run, not a distribution.** It was measured once,
  on 2026-09-07, at temperature 0. Nothing here reports variance across
  repeated runs, and a single pass over 30 cases cannot distinguish a robust
  zero from a lucky one. Only the deterministic column is re-checked
  continuously, by CI.
- **The live run is not reproducible byte-for-byte.** It depends on a hosted
  model behind a version label that can change under us without notice. The
  resume file records the model name so two sittings cannot be blended, but
  nothing pins the weights.
- **The held-out payloads are only partly independent.** They were written
  by a session with no repository access, but the brief was written by a
  repo-aware one, which chose what context to supply (it withheld the
  architecture, the prompts, the deterministic disposition and the citation
  check). Recorded in full in
  [evals/golden/FROZEN.md](evals/golden/FROZEN.md).
- **The agent was modified to fit the infrastructure, twice.** Neither
  change touches the fixtures, labels, payloads or policy, but both are
  changes to the system being measured and are recorded here rather than
  left implicit. `docket.llm.MAX_COMPLETION_TOKENS` caps the per-call
  completion, and the Investigator no longer re-sends the model's own
  `reasoning_content` back into its message history. Both exist because a
  single request on the largest golden case exceeded the free tier's 8,000
  tokens-per-minute ceiling. Dropping self-context could in principle shift
  which tools the model chooses; the documents, tool results and prompts it
  sees are unchanged.
- **The live run is measured across several sittings.** A full run does not
  fit in the free tier's daily token budget, so `--resume` banks completed
  case-runs and the run continues the next day. The harness refuses to merge
  results measured on a different model or with different agent code, and
  the report states which dates the numbers come from.
- **Two held-out payloads name a sibling document.** `apply_overlay`
  attaches to the first goods receipt or invoice on a case; the brief named
  a different one. Both are still coherent attacks, and the text was left
  unedited rather than reworded from inside the repo.

**Capability**

- **No ERP write path of any kind.** `Proposal.can_post` is hardcoded
  `False` and is never model-controlled. There is no posting, payment or
  release capability anywhere in the system, including the UI. What does
  exist -- added after the original scope cut -- is a human-approval gate
  (`interrupt()`) and a web view for exercising it; approving records a note
  to supplier memory and nothing else.
- **Durable approval is single node.** Checkpoints, supplier memory, the
  audit trail and the web UI's run records live in one SQLite file (see
  "Durable approval" above and `ui/README.md`), so a paused approval
  survives a restart. SQLite was chosen because the property under test is
  restart safety, not concurrent approvers on several machines; the UI runs
  one worker and multi-worker operation is untested.
  *(This bullet read "Graph checkpoints and supplier memory are
  process-local ... Nothing here is a persistence design" until 2026-10-14.
  Corrected rather than left standing.)*

**Deliberate non-goals**

- **Langfuse tracing is not implemented.** docs/PROJECT.md 6 names it. It
  appears in this codebase in exactly one place -- the banned-imports list
  in `tests/test_architecture.py`. Cut rather than built: it is
  infrastructure garnish next to the injection result, and pretending
  otherwise would be the overclaim this section exists to prevent.

*(Token budgets were listed here as a non-goal until 2026-09-03, when they
stopped being optional: `docket.llm.MAX_COMPLETION_TOKENS` now caps the
per-call completion, because without it the largest golden case exceeds the
free tier's per-request ceiling and the eval cannot run at all. Both halves
of docs/PROJECT.md 3.3's "step and token budgets per case" therefore exist --
the step budget as the Investigator's four-call cap, the token budget as
that constant.)*

**Authorship**

- **The author is not an ERP functional consultant.** The claim being made
  is agent infrastructure -- permission scoping, grounding discipline,
  measurable guardrails -- against a realistic ERP process. It is not domain
  expertise in accounts payable, and the domain modelling should be read
  with that in mind.

## Web UI

Two views onto the agent, in [`ui/`](ui/README.md): a **case investigation and
approval console** (the ordered tool-call trajectory, every claim with the
document key it rests on, the policy gate's arithmetic, and a real
approve/reject that resumes the graph's `interrupt()` via `Command(resume=...)`)
and a **guardrail-evidence dashboard** (the three metrics, a per-case
breakdown, and the injection-overlay results).

```
.venv/Scripts/pip install -e ".[ui]"
cd ui/web && npm install && npm run build
uvicorn ui.api.app:app --port 8000 --workers 1
```

It is a viewer: it lives outside `src/`, adds no capability to `docket`,
removes none of its constraints, and is excluded from the CI gates so it
cannot be the reason they fail. There is no post button, because there is no
post capability -- `can_post` stays hardcoded `False`. `docs/PROJECT.md`
section 7 records this as a deliberate reversal of its own "no polished UI"
scope cut, and [`ui/README.md`](ui/README.md) explains the rest of the
reasoning, including how untrusted document text is quarantined for the human
reader and why the server, not the client, assigns `proposed_by`.

### Model wiring

The agent nodes need a Groq API key (free tier): create a `.env` file at the
repo root (gitignored; see `.env.example`) with:

```
GROQ_API_KEY=your-key-here
```

`docket.llm.get_chat_model()` reads it and defaults to
`openai/gpt-oss-120b` (tool-calling works reliably there; `openai/gpt-oss-20b`
does not -- see `src/docket/llm.py` for why). Without a model, every graph
node falls back to fully deterministic, network-free logic -- this is what
the test suite uses by default, so it stays fast and reproducible without a
key. Pass `model=get_chat_model()` to `build_docket_graph()` to run the real
agent end to end.

## Provenance

Derived from the BPI Challenge 2019 event log (van Dongen, B.F., 2019),
4TU.ResearchData, DOI 10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1, licensed
CC BY 4.0. Structural properties are derived from the log; all monetary values,
quantities, dispositions and free-text notes are authored for this project.

See [fixtures/frozen/FROZEN.md](fixtures/frozen/FROZEN.md) for the full
provenance chain once the fixture is frozen.

## Development

```
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.lock.txt
ruff check .
mypy
pytest -m "not slow"
pytest -m slow   # full-log checks, ~500MB CSV, ~40s
pytest -m llm    # hits the live Groq API; requires GROQ_API_KEY, see below
```
