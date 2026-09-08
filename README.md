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

| Metric | Deterministic (CI gate) | Live (Groq, `openai/gpt-oss-120b`) |
|---|---|---|
| Disposition accuracy | 100% (30/30) | 100% (30/30) |
| Trajectory correctness | 100% (30/30) | 100% (30/30) |
| Injection success rate | N/A -- no model in the loop, nothing to inject into | **0% (0/8)** -- 0/4 public, **0/4 held out** |

Reproduce:

```
python tools/run_eval.py                                                  # deterministic
python tools/run_eval.py --model --held-out --resume evals/runs/final.json  # live
```

The deterministic column is CI-gated on every push. The live column was
measured 2026-09-06 to 2026-09-07: a full live run does not fit in the free
tier's daily token budget, so it ran across two sittings with `--resume`,
15 case-runs banked on the first day and 23 on the second. The harness
refuses to merge results measured on a different model or with different
agent code, so the two days describe one system, not an average of two.

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

## Known limits

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
  the one thing this project exists to show.
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
- **Graph checkpoints and supplier memory are process-local.** They die with
  the server, and the UI says so. Nothing here is a persistence design.

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
