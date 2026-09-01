# Frozen eval record

This directory is Tier 1 (docs/PROJECT.md section 6.1): immutable once
written. Nothing here is edited to make implementation tests pass. A genuine
correction requires an explicit new freeze act, not a silent label change.

## Provenance

The Day 3 labelled exception set and injection overlays were promoted from:

- `evals/draft/day3_labels_draft.json`
- `evals/draft/injection_overlays_draft.json`

The drafts were reviewed against:

- `docs/PROJECT.md`
- `fixtures/frozen/selection/cases.json`
- `fixtures/rendered/documents/`
- `tools/validate_day3_drafts.py`

Current implementation output was not used as ground truth.

## Contents

- Labelled cases: 30
- Public injection overlays: 4
- Held-out injection overlays: 4
- Held-out payload text: authored 2026-09-01 (see "Freeze act 2" below)

## Freeze act 2 -- held-out payloads authored (2026-09-01)

The four `held_out_overlays` entries had `payload_status:
"to_be_authored_repo_blind_before_final_run"` and no `payload`. They now
carry authored payload text. **This is the planned amendment this file's own
holdout policy describes**, performed as the "explicit new freeze act"
required above -- not a silent label change, and not an edit made to make any
test pass. No other field changed: the four `overlay_id`, `case_id`, `target`
and `success_condition` values, and all four public overlays, are identical
to freeze act 1.

Authorised by the maintainer after the conflict was raised explicitly:
AGENTS.md forbids editing anything under `evals/golden/`, while this file's
`holdout_policy` says the held-out payloads should be authored later, before
the final run. The policy field is the more specific instruction and
describes this exact edit; the manifest below is re-issued to match.

**Authorship.** The payload text was written in a separate session with no
repository access, per docs/PROJECT.md 6.1, and copied in verbatim -- not
reworded by a repo-aware session, which would reintroduce the contamination
the holdout exists to prevent.

One honest qualification on "repo-blind": the *brief* given to that session
was written by a repo-aware session. It deliberately withheld the node
architecture, the Investigator's system prompt, the fact that disposition is
computed deterministically rather than chosen by the model, the evidence-key
citation check, and the four public payloads. It did supply the target
documents' real amounts and identifiers, and each overlay's frozen
`success_condition`. So the payload text itself is uncontaminated, but the
choice of what context to give the author was not fully independent. A reader
weighing the held-out result should know that.

Techniques reported by the authoring session, one per payload:

| Overlay | Technique |
|---|---|
| `inj-holdout-001` | workflow-message spoofing |
| `inj-holdout-002` | forged authority with urgency |
| `inj-holdout-003` | out-of-band settlement claim |
| `inj-holdout-004` | data-correction reframing |

**Known imperfection, recorded rather than corrected.** `apply_overlay`
attaches a note to the *first* goods receipt or invoice on a case. The brief
given to the authoring session named a different document for two overlays,
so `inj-holdout-001`'s payload text refers to `SI44976897523735` while the
note sits on `SI44976897523716`, and `inj-holdout-002` refers to
`INV-297014168387590` while the note sits on `SI297014168387588`. Both remain
coherent attacks -- a billing contact referencing a sibling invoice is
plausible -- and the payloads were deliberately **not** reworded to fix it,
since editing them from a repo-aware session is the contamination this
holdout exists to prevent.

Pre-record manifest root hash for this freeze act (sha256 over the sorted
MANIFEST.sha256 lines with the authored payloads in place, but before this
"Freeze act 2" record was added to FROZEN.md) -- same convention as the
freeze act 1 hash below, since a file cannot state its own hash:

```
119ae0605dbdbfc87f5a8d404d9156a2c74d427ec4574612cffe8236619945ce
```

## Integrity

Pre-record manifest root hash (sha256 over the sorted MANIFEST.sha256 lines
before this record was added):

```
2012230534d0f043175a27d08b6def35d3f85deaee0fe1f7a8d9cad583bdb1c3
```

Verify the final manifest with:

```
python -c "from pathlib import Path; from docket.manifest import verify_manifest; print(verify_manifest(Path('evals/golden'), Path('evals/golden/MANIFEST.sha256')))"
```
