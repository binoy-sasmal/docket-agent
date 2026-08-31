# Agent-facing rules for this repository

Read `docs/PROJECT.md` in full before writing any code in this repository. It is
the authoritative description of the project.

## The one rule that overrides everything else

**Never edit, regenerate, or delete anything under `fixtures/frozen/` or
`evals/golden/`.** These are the frozen selection, the labelled exception set,
and the eval assertions. They are authored before any agent code exists and
frozen by content hash so that the agent under test cannot influence the ground
truth it is measured against (see `docs/PROJECT.md` §6.1).

If a test against these fails, **the implementation is wrong, not the label.**
Fix the code. Do not edit the fixture, the label, or the assertion to make the
test pass, no matter how obviously wrong the label looks -- flag it to the human
maintainer instead and let them decide, with a recorded reason, whether it needs
correction.

`fixtures/rendered/` is a different, adjacent directory: the rendered JSON
documents. It is committed and manifest-pinned, but deliberately re-issuable --
if you find a genuine defect there (e.g. a wrong SAP field name), you may
re-render and re-issue its manifest as an explicit, visible step, but never as a
side effect of an unrelated change.

## Architecture invariants (grow over Sessions 3+, hold from Session 1 on)

- The Reconciler node holds **zero tools**. Not "just one lookup." Its node
  function must not even accept a tool-executor parameter.
- The Policy gate contains **no LLM call**. Deterministic Python only. Its module
  must not import a model client, directly or transitively.
- Every claim in agent output must carry a document key (PO line, material
  document, invoice item) or it does not count as evidence.
- All document free text is untrusted input.

See `docs/PROJECT.md` §3 for the full architecture and the reasoning behind it.
