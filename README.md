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

## Status

BPIC 2019 derivation is hand-checked and frozen: the case selection lives in
`fixtures/frozen/`, ~300 line items are rendered to `fixtures/rendered/`
(see [docs/handcheck/](docs/handcheck/) for the review record). The Day 3
golden eval set (30 labelled cases, 4 public + 4 held-out injection overlays)
is frozen in `evals/golden/`.

The four-node graph (Investigator, Reconciler, Policy gate, Proposer) runs on
real LangGraph, with `interrupt()` gating the human-approval/memory-write
step -- the agent cannot post without approval (`tests/test_approval_memory.py`).
The Policy gate is deterministic Python with no model in its import graph;
the Reconciler holds no tools. A real chat model (Groq, via `langchain-groq`)
now drives the Investigator's tool-calling loop, the Reconciler's narrative,
and the Proposer's justification text -- see "Model wiring" below. An
eval-time overlay mechanism (`docket.tools.injection`) attaches injection
payloads to in-memory document copies without touching frozen fixtures.

The eval harness (`docket.eval_harness`, `tools/run_eval.py`) runs the
golden 30 through the graph and reports the three metrics from
docs/PROJECT.md section 6. Deterministic mode is what CI gates on
(`tests/test_eval_harness.py`, plus a dedicated `run_eval.py` CI step) --
free, fast, no API key needed:

| Metric | Deterministic | Live (Groq, `openai/gpt-oss-120b`) |
|---|---|---|
| Disposition accuracy | 100% (30/30) | pending re-verification |
| Trajectory correctness | 100% (30/30) | pending re-verification |
| Injection success rate | N/A -- no model in the loop, nothing to inject into | pending re-verification |

The deterministic numbers above are current and CI-gated. An earlier live
run reported 100%/100%/0%, but that run predates a fix to a real bug (the
Reconciler/Proposer prompts were not actually receiving evidence keys, so a
citation-completeness check has since been added to the injection metric)
and is void -- report honestly, not the flattering stale number. A rerun of
`python tools/run_eval.py --model` is currently blocked by the free-tier
Groq key's daily token budget (200,000 TPD) being exhausted from this
session's testing; retrying does not help until the quota rolls over.
Live numbers will be filled in once that rerun happens.

Still open: re-running the live eval once Groq quota resets; authoring the
four held-out injection payloads in a separate, repo-blind session (the
harness only scores the 4 public overlays so far, and per docs/PROJECT.md
6.1 the point of holding four out is that a system cannot be shown to
defend against an attack it was tuned against); step/token budget
guardrails beyond the Investigator's tool-call cap; Langfuse tracing.

Full derivation record -- reconnaissance findings, exclusions, the schema,
and every modelling assumption -- is in
[docs/DERIVATION.md](docs/DERIVATION.md).

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
