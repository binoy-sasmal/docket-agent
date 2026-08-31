"""Shared manifest utilities for both fixture tiers.

Used by derive/render.py (Tier 2, fixtures/rendered/) and freeze.py (Tier 1,
fixtures/frozen/) -- deliberately placed outside src/docket/derive/ so that
freeze.py, which is the only module allowed to write fixtures/frozen/, does
not have to import anything from the package the architecture test
(tests/test_architecture.py) restricts.

Format: sha256sum -c compatible ("<hex digest>  <relative path>\n" per
line, sorted by path), plus a single root hash over those lines -- one
number to quote in FROZEN.md / the README (docs/PROJECT.md section 6.1).
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest_lines(directory: Path, files: list[Path]) -> list[str]:
    """One "<sha256>  <relative-posix-path>" line per file, sorted by path."""
    lines = []
    for path in files:
        rel = path.relative_to(directory).as_posix()
        lines.append(f"{_sha256_of_file(path)}  {rel}")
    return sorted(lines)


def root_hash(manifest_lines: list[str]) -> str:
    """A single hash over the sorted manifest lines -- changes if any file's
    content, path, or the file set itself changes.
    """
    digest = hashlib.sha256()
    for line in manifest_lines:
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def write_manifest(directory: Path, manifest_path: Path) -> str:
    """Walk every file under `directory` (except the manifest itself),
    write a sha256sum-compatible MANIFEST at `manifest_path`, and return the
    root hash.
    """
    files = sorted(
        p for p in directory.rglob("*") if p.is_file() and p.resolve() != manifest_path.resolve()
    )
    lines = build_manifest_lines(directory, files)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
        for line in lines:
            handle.write(line + "\n")
    return root_hash(lines)


def verify_manifest(directory: Path, manifest_path: Path) -> tuple[bool, list[str]]:
    """Recompute hashes for every file under `directory` and compare against
    manifest_path. Returns (all_match, list_of_problem_descriptions).
    """
    if not manifest_path.exists():
        return False, [f"manifest not found: {manifest_path}"]

    recorded: dict[str, str] = {}
    with manifest_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line:
                continue
            digest, _, rel = line.partition("  ")
            recorded[rel] = digest

    actual_files = sorted(
        p for p in directory.rglob("*") if p.is_file() and p.resolve() != manifest_path.resolve()
    )
    actual: dict[str, str] = {
        p.relative_to(directory).as_posix(): _sha256_of_file(p) for p in actual_files
    }

    problems: list[str] = []
    for rel, digest in recorded.items():
        if rel not in actual:
            problems.append(f"missing file (recorded in manifest but absent on disk): {rel}")
        elif actual[rel] != digest:
            problems.append(f"content mismatch: {rel}")
    for rel in actual:
        if rel not in recorded:
            problems.append(f"extra file (on disk but not in manifest): {rel}")

    return (len(problems) == 0), problems
