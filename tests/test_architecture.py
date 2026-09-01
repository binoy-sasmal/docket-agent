"""Architecture invariants from docs/PROJECT.md, enforced as tests."""

from __future__ import annotations

import ast
import inspect
import tomllib
from pathlib import Path

from docket.graph.langgraph_app import policy_gate_node, reconciler_node
from docket.graph.skeleton import policy_gate, reconciler
from docket.tools.odata import ReadOnlyODataTools

REPO_ROOT = Path(__file__).resolve().parent.parent
DERIVE_DIR = REPO_ROOT / "src" / "docket" / "derive"
SCHEMA_DIR = REPO_ROOT / "src" / "docket" / "schema"
POLICY_MODULE = REPO_ROOT / "src" / "docket" / "policy.py"

# Any model-client library that could make an LLM call. LangGraph is an
# orchestrator and is checked separately so policy.py can remain deterministic.
# Membership is exact-match on the import's top-level module name, so a new
# package (e.g. adding a different model provider) must be listed here by
# its actual import name, not assumed to be caught by a prefix.
MODEL_CLIENT_LIBRARY_PREFIXES = (
    "langchain",
    "langchain_core",
    "langchain_groq",
    "langfuse",
    "anthropic",
    "openai",
    "groq",
)
POLICY_FORBIDDEN_IMPORT_PREFIXES = MODEL_CLIENT_LIBRARY_PREFIXES + ("langgraph",)


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


def test_schema_and_derive_import_no_model_client_library() -> None:
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
                    if name.split(".")[0].lower() in MODEL_CLIENT_LIBRARY_PREFIXES:
                        offenders.append(f"{path.relative_to(REPO_ROOT)} imports {name!r}")

    assert not offenders, (
        "src/docket/schema/ and src/docket/derive/ must not import any model-client "
        "library in Session 1. Found:\n" + "\n".join(offenders)
    )


def test_langgraph_is_declared_as_orchestration_dependency() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]

    assert any(dependency.startswith("langgraph") for dependency in dependencies)


def test_policy_gate_module_imports_no_llm_library() -> None:
    tree = ast.parse(POLICY_MODULE.read_text(encoding="utf-8"), filename=str(POLICY_MODULE))
    offenders: list[str] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]

        for name in names:
            if name.split(".")[0].lower() in POLICY_FORBIDDEN_IMPORT_PREFIXES:
                offenders.append(name)

    assert not offenders, "policy.py must not import model or graph libraries: " + ", ".join(
        offenders
    )


def test_reconciler_nodes_accept_no_tool_executor() -> None:
    assert tuple(inspect.signature(reconciler).parameters) == ("investigation",)
    assert tuple(inspect.signature(reconciler_node).parameters) == ("state",)


def test_policy_gate_nodes_have_deterministic_signatures() -> None:
    assert tuple(inspect.signature(policy_gate).parameters) == ("reconciliation",)
    assert tuple(inspect.signature(policy_gate_node).parameters) == ("state",)


def test_odata_tool_public_methods_are_allowlisted_reads() -> None:
    public_methods = {
        name
        for name, member in inspect.getmembers(ReadOnlyODataTools, inspect.isfunction)
        if not name.startswith("_")
    }

    assert public_methods == set(ReadOnlyODataTools.ALLOWED_TOOL_NAMES)
    assert all(name.startswith(("get_", "list_")) for name in public_methods)
