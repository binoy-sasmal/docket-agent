"""The one canonical JSON serialiser for anything that will be content-hashed.

Every writer of fixtures/rendered/ or fixtures/frozen/ must go through this
module. Without a single canonical form, byte-for-byte content hashes are
noise -- two semantically identical documents could hash differently because
of key order, float formatting, or line-ending differences. See
docs/PROJECT.md section 6.1 and CLAUDE.md.

Rules:
- UTF-8, LF line endings, trailing newline.
- Keys sorted.
- 2-space indent.
- decimal.Decimal serialised as a string, never as a JSON number -- a JSON
  number round-trips through float in most readers, which is exactly the
  precision loss this project cannot afford (see docs/DERIVATION.md 1.10 on
  the source's E-notation values).
- datetime serialised as ISO-8601 with an explicit UTC offset.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


def _default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            raise ValueError(
                f"datetime {obj!r} has no timezone; canonical serialisation "
                "requires an explicit UTC offset."
            )
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not canonically serialisable")


def canonical_json(data: Any) -> str:
    """Serialise data to the canonical JSON string form. Ends with exactly
    one trailing newline; every line uses LF only.
    """
    text = json.dumps(
        data,
        default=_default,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
    )
    return text + "\n"


def write_canonical_json(path: Path, data: Any) -> None:
    """Write data to path in canonical form. Always LF, always UTF-8, no BOM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = canonical_json(data)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
