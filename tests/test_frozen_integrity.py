"""The load-bearing test for constraint 1 (docs/PROJECT.md section 6.1):
nothing under fixtures/frozen/ or evals/golden/ may be edited once written.

Before a freeze has happened (the current state, as of this commit -- the
freeze is the last act of Session 1, gated on a human hand-check sign-off
per docs/DERIVATION.md section 4 / freeze.py), this test is skipped rather
than passing vacuously, so its status honestly reflects "not yet applicable"
rather than "verified". Once fixtures/frozen/MANIFEST.sha256 exists, this
test recomputes every file's hash and fails loudly on any mismatch -- this
is what a `git checkout`, a careless edit, or a bad merge would trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docket.manifest import verify_manifest

REPO_ROOT = Path(__file__).resolve().parent.parent
FROZEN_DIR = REPO_ROOT / "fixtures" / "frozen"
FROZEN_MANIFEST = FROZEN_DIR / "MANIFEST.sha256"
GOLDEN_DIR = REPO_ROOT / "evals" / "golden"
GOLDEN_MANIFEST = GOLDEN_DIR / "MANIFEST.sha256"


@pytest.mark.skipif(
    not FROZEN_MANIFEST.exists(),
    reason="fixtures/frozen/ has not been frozen yet (freeze.py has not run)",
)
def test_frozen_selection_matches_its_manifest() -> None:
    ok, problems = verify_manifest(FROZEN_DIR, FROZEN_MANIFEST)
    assert ok, "fixtures/frozen/ does not match MANIFEST.sha256:\n" + "\n".join(problems)


@pytest.mark.skipif(
    not GOLDEN_MANIFEST.exists(),
    reason="evals/golden/ has no manifest yet (labels are authored in Session 2)",
)
def test_golden_evals_match_their_manifest() -> None:
    ok, problems = verify_manifest(GOLDEN_DIR, GOLDEN_MANIFEST)
    assert ok, "evals/golden/ does not match MANIFEST.sha256:\n" + "\n".join(problems)
