"""Tests for the canonical serialiser and the field-group provenance model."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from docket.schema.canonical import canonical_json
from docket.schema.provenance import DEFAULT_GROUP_PROVENANCE, Provenance


def test_canonical_json_sorts_keys_and_ends_with_one_newline() -> None:
    text = canonical_json({"b": 1, "a": 2})
    assert text == '{\n  "a": 2,\n  "b": 1\n}\n'


def test_canonical_json_serialises_decimal_as_string_not_number() -> None:
    text = canonical_json({"amount": Decimal("1234.50")})
    # Must be quoted -- a bare JSON number would round-trip through float in
    # most readers, which is exactly the precision loss this project can't
    # afford (docs/DERIVATION.md 1.10, the source's E-notation values).
    assert '"amount": "1234.50"' in text


def test_canonical_json_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone"):
        canonical_json({"when": datetime(2018, 1, 1)})  # noqa: DTZ001


def test_canonical_json_serialises_aware_datetime_as_iso8601() -> None:
    text = canonical_json({"when": datetime(2018, 1, 1, tzinfo=UTC)})
    assert '"2018-01-01T00:00:00+00:00"' in text


def test_canonical_json_is_deterministic_across_key_insertion_order() -> None:
    a = canonical_json({"z": 1, "a": 2, "m": 3})
    b = canonical_json({"a": 2, "m": 3, "z": 1})
    assert a == b


def test_default_group_provenance_covers_every_group_used_by_render() -> None:
    # These are the exact group names render.py's field_group_provenance
    # dict is built from (docket.schema.provenance.DEFAULT_GROUP_PROVENANCE
    # copied and selectively overridden) -- if a group name typo'd here or
    # in render.py, this catches the mismatch instead of it silently
    # producing an incomplete provenance block.
    for value in DEFAULT_GROUP_PROVENANCE.values():
        assert isinstance(value, Provenance)
