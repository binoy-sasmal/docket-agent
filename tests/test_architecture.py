"""Architecture invariants from docs/PROJECT.md, enforced as tests rather than
convention.

Per the Session 1 plan: the pre-commit hook and read-only bits that would
otherwise guard fixtures/frozen/ are deliberately not used in this project.
This test file -- run in the fast default suite, on every push -- is therefore
the one active enforcement layer for the structural separation described in
docs/PROJECT.md's Session 1 plan. It must keep passing.

Clauses for Session 3+ (Reconciler zero-tools, Policy gate no-LLM) are listed
here as documentation of what must be added when those modules exist; they are
not yet checkable because the modules do not exist.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DERIVE_DIR = REPO_ROOT / "src" / "docket" / "derive"
SCHEMA_DIR = REPO_ROOT / "src" / "docket" / "schema"

# Any library that could make an LLM call. Extend this list as new LLM/agent
# dependencies are added to the project in later sessions.
LLM_LIBRARY_PREFIXES = (
    "langchain",
    "langgraph",
    "langfuse",
    "anthropic",
    "openai",
)


def _python_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.rglob("*.py"))


def test_derive_never_references_the_frozen_path() -> None:
    """derive/ may write fixtures/derived/ and fixtures/rendered/, but the
    string "fixtures/frozen" (in any spelling) must not appear anywhere in it.
    Only src/docket/freeze.py is allowed to write fixtures/frozen/ -- that
    module lives outside this directory precisely so this check is meaningful.

    This is the load-bearing check for constraint 1 (nothing under
    fixtures/frozen/ or evals/golden/ may ever be edited once written): it
    verifies the *capability* to write there does not exist in the derivation
    pipeline, rather than merely asking people not to use it.
    """
    forbidden_needles = ("fixtures/frozen", "fixtures\frozen")
    offenders: list[str] = []

    for path in _python_files(DERIVE_DIR):
        text = path.read_text(encoding="utf-8")
        for needle in forbidden_needles:
            if needle in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)} contains {needle!r}")

    assert not offenders, (
        "derive/ must never reference the frozen fixture path -- only "
        "freeze.py may write fixtures/frozen/. Found:\n" + "\n".join(offenders)
    )


def test_schema_and_derive_import_no_llm_library() -> None:
    """Session 1 produces no agent code (constraint 4). This is checkable: the
    schema and derivation modules must not import any LLM/agent library, so
    that the commit freezing the fixture selection is provably from a
    lockfile that could not have called a model.
    """
    offenders: list[str] = []

    for directory in (DERIVE_DIR, SCHEMA_DIR):
        for path in _python_files(directory):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]

                for name in names:
                    if name.split(".")[0].lower() in LLM_LIBRARY_PREFIXES:
                        offenders.append(f"{path.relative_to(REPO_ROOT)} imports {name!r}")

    assert not offenders, (
        "src/docket/schema/ and src/docket/derive/ must not import any LLM "
        "library in Session 1. Found:\n" + "\n".join(offenders)
    )


def test_no_llm_library_in_the_lockfiles_yet() -> None:
    """Belt-and-braces on constraint 4: as of Session 1, the dependency set
    itself must not contain an LLM/agent library. This test is expected to
    start failing in Session 3+, at which point it should be deleted -- its
    job is only to make Session 1's boundary visible and checkable while it
    is supposed to hold.
    """
    lockfiles = [
        REPO_ROOT / "requirements.lock.txt",
        REPO_ROOT / "requirements-dev.lock.txt",
    ]
    offenders: list[str] = []

    for lockfile in lockfiles:
        if not lockfile.exists():
            continue
        text = lockfile.read_text(encoding="utf-8").lower()
        for prefix in LLM_LIBRARY_PREFIXES:
            if prefix in text:
                offenders.append(f"{lockfile.name} mentions {prefix!r}")

    assert not offenders, (
        "Session 1's lockfiles must not pull in an LLM library. Found:\n"
        + "\n".join(offenders)
    )


# --- Documented, not yet checkable: add these when the modules exist (Session 3+) ---
#
# - Reconciler: its node function must accept no tool-executor parameter at
#   all, and must bind a model client with no tools attached. A test asserting
#   `tools == []` is weaker than this -- a list is a thing you can append to.
# - Policy gate: its module's transitive imports must be disjoint from the
#   LLM dependency set (see LLM_LIBRARY_PREFIXES above). No LLM call, ever.
