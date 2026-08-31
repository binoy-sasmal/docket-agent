# Frozen fixture record

This directory is Tier 1 (docs/PROJECT.md section 6.1): immutable once
written. Nothing here is ever edited -- a failing test means the
implementation is wrong, not this record.

## Provenance

Derived from the BPI Challenge 2019 event log (van Dongen, B.F., 2019), 4TU.ResearchData, DOI 10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1, licensed CC BY 4.0. Structural properties are derived from the log; all monetary values, quantities, dispositions and free-text notes are authored for this project.

## Selection

- Selected cases: 300
- Excluded before sampling: 10,512
- Eligible pool: 241,222
- Hash salt: `docket-bpic2019-session1`
- Vendor cap: 6

See docs/DERIVATION.md for the full reconnaissance, exclusion, and
stratification record, and docs/handcheck/ for the human-verified hand-check
reports this freeze depended on.

## Integrity

Root manifest hash (sha256 over the sorted MANIFEST.sha256 lines):

```
b29eb6481e93407c533469fa8e058e879e17011a23d508daa6947c4dba8e18dc
```

Verify with:

```
python -c "from pathlib import Path; from docket.manifest import verify_manifest; \
print(verify_manifest(Path('fixtures/frozen'), Path('fixtures/frozen/MANIFEST.sha256')))"
```
