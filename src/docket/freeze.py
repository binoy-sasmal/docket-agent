"""Promote the derived selection into the frozen Tier 1 fixture.

This is the ONLY module in the whole project allowed to write under
fixtures/frozen/ or evals/golden/ (docs/PROJECT.md section 6.1, CLAUDE.md).
It lives outside src/docket/derive/ specifically so that constraint is
checkable: tests/test_architecture.py asserts the string "fixtures/frozen"
appears nowhere under derive/, which would be meaningless if this module
lived there too.

Per the Session 1 plan (docs/DERIVATION.md section 4 / the plan's B7),
freezing is the LAST act of the session, after the human hand-check sign-off
(docs/handcheck/VERIFIED.md) -- not before. `promote()` enforces this by
refusing to run unless VERIFIED.md exists and every case named in
HANDCHECK_CASES has a completed reviewer line in it. This is a best-effort
machine check on a human process, not a replacement for actually reading the
sign-off -- but it stops the freeze from happening by simple oversight
before the review has occurred.

`promote()` also refuses to run if fixtures/frozen/ is already non-empty --
freezing is one-way. To fix a mistake discovered after a freeze, see
docs/PROJECT.md section 6.1: the fixture, the labels and the eval assertions
are frozen by content hash and committed; a genuine correction is a new,
explicitly-recorded act (FREEZE-OVERRIDE in the commit message), never a
silent edit.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from docket.derive.handcheck import HANDCHECK_CASES
from docket.manifest import write_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
DERIVED_SELECTION_PATH = REPO_ROOT / "fixtures" / "derived" / "selection" / "cases.json"
FROZEN_DIR = REPO_ROOT / "fixtures" / "frozen"
FROZEN_SELECTION_PATH = FROZEN_DIR / "selection" / "cases.json"
FROZEN_MANIFEST_PATH = FROZEN_DIR / "MANIFEST.sha256"
FROZEN_RECORD_PATH = FROZEN_DIR / "FROZEN.md"
HANDCHECK_VERIFIED_PATH = REPO_ROOT / "docs" / "handcheck" / "VERIFIED.md"

ATTRIBUTION = (
    "Derived from the BPI Challenge 2019 event log (van Dongen, B.F., 2019), "
    "4TU.ResearchData, DOI 10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1, "
    "licensed CC BY 4.0. Structural properties are derived from the log; all "
    "monetary values, quantities, dispositions and free-text notes are "
    "authored for this project."
)


class FreezeBlocked(Exception):
    """Raised when promote() refuses to run. The message explains why."""


def _check_handcheck_signoff() -> None:
    if not HANDCHECK_VERIFIED_PATH.exists():
        raise FreezeBlocked(
            f"{HANDCHECK_VERIFIED_PATH} does not exist. The hand-check gate "
            "(docs/PROJECT.md section 7, Day 1 gate 1) requires a human to "
            "review the three reports in docs/handcheck/ against the raw "
            "event rows and sign off before the selection can be frozen. "
            "This is not a step to skip or perform on the model's own "
            "authority."
        )
    text = HANDCHECK_VERIFIED_PATH.read_text(encoding="utf-8")
    missing = [case_id for case_id in HANDCHECK_CASES if case_id not in text]
    if missing:
        raise FreezeBlocked(
            f"{HANDCHECK_VERIFIED_PATH} exists but does not mention every "
            f"hand-checked case. Missing: {missing}"
        )


def _check_target_empty() -> None:
    if FROZEN_DIR.exists() and any(FROZEN_DIR.iterdir()):
        raise FreezeBlocked(
            f"{FROZEN_DIR} is not empty. Freezing is one-way -- see this "
            "module's docstring and docs/PROJECT.md section 6.1 for how to "
            "handle a genuine correction."
        )


def promote() -> str:
    """Copy the derived selection into fixtures/frozen/, write
    MANIFEST.sha256 and FROZEN.md, and return the root hash. Refuses to run
    without a hand-check sign-off or onto a non-empty target.
    """
    _check_handcheck_signoff()
    _check_target_empty()

    if not DERIVED_SELECTION_PATH.exists():
        raise FreezeBlocked(
            f"{DERIVED_SELECTION_PATH} does not exist -- run "
            "`python -m docket.derive.sample` first."
        )

    FROZEN_SELECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(DERIVED_SELECTION_PATH, FROZEN_SELECTION_PATH)

    root = write_manifest(FROZEN_DIR, FROZEN_MANIFEST_PATH)

    selection = json.loads(DERIVED_SELECTION_PATH.read_text(encoding="utf-8"))
    frozen_record = f"""# Frozen fixture record

This directory is Tier 1 (docs/PROJECT.md section 6.1): immutable once
written. Nothing here is ever edited -- a failing test means the
implementation is wrong, not this record.

## Provenance

{ATTRIBUTION}

## Selection

- Selected cases: {len(selection["selected_case_ids"])}
- Excluded before sampling: {selection["excluded_count"]:,}
- Eligible pool: {selection["eligible_count"]:,}
- Hash salt: `{selection["hash_salt"]}`
- Vendor cap: {selection["vendor_cap"]}

See docs/DERIVATION.md for the full reconnaissance, exclusion, and
stratification record, and docs/handcheck/ for the human-verified hand-check
reports this freeze depended on.

## Integrity

Root manifest hash (sha256 over the sorted MANIFEST.sha256 lines):

```
{root}
```

Verify with:

```
python -c "from pathlib import Path; from docket.manifest import verify_manifest; \\
print(verify_manifest(Path('fixtures/frozen'), Path('fixtures/frozen/MANIFEST.sha256')))"
```
"""
    FROZEN_RECORD_PATH.write_text(frozen_record, encoding="utf-8", newline="\n")

    # FROZEN.md is written after the manifest, so it is not itself covered
    # by the hash it reports -- recompute once more to cover it too.
    return write_manifest(FROZEN_DIR, FROZEN_MANIFEST_PATH)


if __name__ == "__main__":
    try:
        root = promote()
    except FreezeBlocked as exc:
        print(f"FREEZE BLOCKED: {exc}")
        raise SystemExit(1) from exc
    print(f"Frozen. Root hash: {root}")
