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
- Held-out payload text: not authored in this repo-aware session

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
