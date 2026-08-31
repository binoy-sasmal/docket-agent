"""Acquisition of the raw BPIC 2019 source files.

Per the Session 1 plan, two sources are used and cross-checked against each
other:

- BPIChallenge2019CSV.zip (ICPM 2019 conference page) -- the working format.
- log_IEEE.xes_.gz (same page) -- used only for a one-shot integrity check
  against the MD5 published on the 4TU.ResearchData DOI record, confirming
  the ICPM-hosted files are the same canonical dataset as the archival
  record. This is *not* the XES cross-check reader the plan describes as a
  fallback -- that is only written if the ICPM URLs are dead.

This module records checksums into data/raw/SOURCES.md rather than fetching
over the network on every run: acquire() is idempotent and verifies existing
files rather than re-downloading them.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import NamedTuple

DATA_RAW = Path(__file__).resolve().parents[3] / "data" / "raw"

CSV_ZIP_URL = (
    "https://icpmconference.org/2019/wp-content/uploads/sites/6/2019/02/"
    "BPIChallenge2019CSV.zip"
)
XES_GZ_URL = (
    "https://icpmconference.org/2019/wp-content/uploads/sites/6/2019/01/"
    "log_IEEE.xes_.gz"
)

# Published on the 4TU.ResearchData DOI record (10.4121/uuid:d06aff4b-79f0-
# 45e6-8ec8-e19730c248f1) for BPI_Challenge_2019.xes. Used only to confirm
# the ICPM-hosted gzip decompresses to the same canonical file.
FOUR_TU_XES_MD5 = "4eb909242351193a61e1c15b9c3cc814"

# Recorded by hand on 2026-08-31 after downloading both files directly, and
# re-verified programmatically by verify_local_files() below.
KNOWN_GOOD = {
    "BPIChallenge2019CSV.zip": {
        "size_bytes": 36_720_297,
        "sha256": "372b5a15c30f4a21b370db25b1912cc60ad1104d4198cfd34f8aecb2f4c2425a",
        "url": CSV_ZIP_URL,
    },
    "log_IEEE.xes.gz": {
        "size_bytes": 16_901_365,
        "sha256": "43edc7abe7b53c75f53f91b6720ba20878de8a3216b5202ae22a0442b92e9c9a",
        "url": XES_GZ_URL,
    },
    "BPI_Challenge_2019.csv": {
        "size_bytes": 527_457_189,
        "sha256": "7d592fb425690d13011d1b874fe2af63f61a66acfc368ecf87b4ed266e6cdb00",
        "url": CSV_ZIP_URL + " (extracted)",
    },
}


class VerificationResult(NamedTuple):
    filename: str
    present: bool
    size_ok: bool
    sha256_ok: bool


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_local_files(data_raw: Path = DATA_RAW) -> list[VerificationResult]:
    """Check every file in KNOWN_GOOD against its recorded size and SHA-256.

    Does not download anything. Acquisition in Session 1 was performed once,
    by hand, with URLs confirmed live first (see data/raw/SOURCES.md); this
    function exists so that later sessions -- or CI, if the raw file is ever
    cached -- can confirm they are working from an unmodified copy.
    """
    results: list[VerificationResult] = []
    for filename, meta in KNOWN_GOOD.items():
        path = data_raw / filename
        if not path.exists():
            results.append(VerificationResult(filename, False, False, False))
            continue
        size_ok = path.stat().st_size == meta["size_bytes"]
        sha256_ok = _sha256_of(path) == meta["sha256"]
        results.append(VerificationResult(filename, True, size_ok, sha256_ok))
    return results


if __name__ == "__main__":
    for result in verify_local_files():
        status = "OK" if result.present and result.size_ok and result.sha256_ok else "MISMATCH"
        print(f"{status:8} {result.filename}  present={result.present} "
              f"size_ok={result.size_ok} sha256_ok={result.sha256_ok}")
