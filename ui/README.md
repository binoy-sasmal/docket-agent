# Docket web UI

Two views onto the existing agent: a **case investigation / approval console**
and a **guardrail-evidence dashboard**. This is a viewer. It adds no capability
to `docket` and removes none of its constraints.

- `ui/api/` — FastAPI service holding the compiled LangGraph app
- `ui/web/` — Vite + React + TypeScript + Tailwind client

## Running it

The API needs the `ui` extra:

```
.venv/Scripts/pip install -e ".[ui]"
```

**Development** (two processes, hot reload):

```
uvicorn ui.api.app:app --port 8000 --workers 1 --reload
cd ui/web && npm install && npm run dev      # http://localhost:5173
```

The Vite dev server proxies `/api` to port 8000.

**Single process** (the API serves the built client at `http://127.0.0.1:8000`):

```
cd ui/web && npm install && npm run build
uvicorn ui.api.app:app --port 8000 --workers 1
```

`--workers 1` is not optional. See "Process-local state" below.

## Why it is shaped this way

### It lives outside `src/`

`docket` is the system under test; this is a viewer onto it. Keeping them apart
means `pyproject.toml`'s strict mypy gate (`files = ["src", "tools"]`) and the
`where = ["src"]` package boundary still cover exactly what they covered before
the UI existed, CI never installs a web server, and nothing here can be
imported by `docket` — so no UI concern can reach the architecture invariants
in `tests/test_architecture.py`.

### There is no post button

`Proposal.can_post` is hardcoded `False` in `docket.graph.skeleton.proposer`
and is never model-controlled. No endpoint posts, pays, releases or clears
anything, because no such capability exists. The one state-changing route,
`POST /api/runs/{run_id}/decision`, resumes the graph's approval `interrupt()`
via `Command(resume=...)`. Approving writes one episodic record to supplier
memory — a note about a past case, not an ERP write. Rejecting writes nothing:
`record_approved_resolution` raises before it touches the store.

### Segregation of duties is enforced server-side

`proposed_by` is set by the server from what actually produced the proposal
(`agent:deterministic`, or `agent:groq:<model>`) and is **never accepted from
the client**. `docket.approval.record_approved_resolution` refuses a write
where `approved_by == proposed_by`; a client able to supply both halves of that
comparison could satisfy the check while it meant nothing. The approver types
their own identity, and the API re-checks before resuming.

### Untrusted text is quarantined, not rendered

`AGENTS.md`: *all document free text is untrusted input.* That rule does not
stop at the agent — a note that cannot instruct the Investigator can still try
to instruct the human reading the screen, which is the softer target. Every
`Note` field is returned in its own `untrusted_notes` array, tagged with the
document key it came from, and rendered escaped inside a labelled quarantine
block. It is never parsed, never linkified, and never used to prefill an
approval decision or reason.

Normally there is nothing to show: `fixtures/frozen/` and `fixtures/rendered/`
carry no note text at all. Notes appear only when an eval injection overlay is
applied to an in-memory copy of a document. **Nothing on disk is ever
modified.**

### Injection overlays are live-mode only

`build_docket_graph` applies overlays only on the model path. With `model=None`
no node reads document free text, so an overlay has nothing to reach. The API
refuses that combination with an explanation rather than accepting an overlay
that would silently do nothing.

Only the four **public** overlays are selectable. The four held-out payloads
stay unauthored (`load_held_out_overlays` raises `OverlayNotAuthored`) until
they are written in a separate, repo-blind session — a system cannot be shown
to defend against an attack it was tuned against.

### Golden labels are marked as labels

Where the UI shows an expected disposition it is explicitly the authored ground
truth, never mixed in with agent output. Conflating the two would be the UI
equivalent of an agent grading its own homework.

### Numbers are computed, never stored

The dashboard runs the real harness (`docket.eval_harness.run_eval`) on
request — the golden 30 take a few seconds deterministically. No results file
is read, so no displayed number can drift from the code or be edited.

A live-model run happens on a background thread because it makes several model
calls per case and can take minutes. Its failures are shown verbatim: a failed
or never-run live eval leaves the live numbers **unverified**, which is not a
licence to display an earlier or estimated figure in their place.

### Process-local state

The graph uses `InMemorySaver` and `SupplierMemoryStore` is an in-memory dict.
Both die with the server, and the UI says so. A durable checkpointer underneath
a still-volatile memory store would make the durability story misleading in
exactly the place the project's claims live — approved writes.

This is why `--workers 1` matters: a resumed `interrupt()` must reach the same
checkpointer instance that created it, and a second worker process would have
its own.

The checkpoint serializer is given an **explicit allowlist** of the types the
graph puts into its state (`_CHECKPOINT_TYPES` in `ui/api/state.py`). LangGraph
currently allows any type with a deprecation warning and documents that this
becomes strict — and resume is the human-approval path, not somewhere to
discover a breaking change later.

## Design

Light, calm, data-dense. Cards on a tinted page, 6px radii, a soft elevation
scale, and a sans-first type system. Density comes from tight consistent
spacing, not from small text.

This replaced a dark brutalist treatment that was genuinely tiring to read: 10
to 12px monospace, uppercase with wide tracking, for every label on the page,
over a near-black ground with a noise overlay. The lesson worth keeping is that
a tool someone stares at while making a careful decision has to be comfortable
first and characterful second. Concretely:

- **Sans for prose and labels; monospace only for machine identifiers** —
  document keys, thread ids, reason codes, numeric columns. Monospace is
  load-bearing where characters get compared one by one, and noise everywhere
  else.
- **Nothing carrying meaning below 12px**, and sentence case for labels.
  Uppercase micro-tracking survives in one utility, for structural headers.
- **One primary action per screen.** Approve is the only filled button in the
  approval panel.

Chrome and data marks are still governed separately. Chart marks use a single
series hue — dispositions are nominal categories, so bar length already encodes
the count and shading bars by size would double-encode it. State uses the
reserved status tokens, always paired with a glyph and a written label so
colour never carries meaning alone.

**Status marks and status text are different values on a light ground**, and
this is measured, not stylistic: the validated status yellow (`#fab219`) is
1.83:1 on white — fine as a filled dot, illegible as a word. So each status
tone carries a `mark` (the validated hue, ≥3:1, for dots and borders) and an
`ink` (a darkened member of the same hue family, ≥4.5:1, for the label). Every
text colour in `index.css` was checked against the surface it actually renders
on; the ratios are in the comments there.

There is exactly one red, and it always means *a human must look at this*:
injection payloads, quarantined free text, failed cases, the approval gate.

No webfont is loaded. This runs on localhost, sometimes offline, and a
render-blocking external font is a poor trade for a tool whose whole job is to
be readable immediately.
