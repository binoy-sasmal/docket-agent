"""Field-group provenance tagging.

Per docs/DERIVATION.md section 3.1, provenance is tagged at the field-GROUP
level, not per individual field -- one tag covers e.g. "all monetary fields
on a rendered invoice item", not each field separately. This is what makes
docs/PROJECT.md section 4.4's honesty requirement structural: every rendered
document carries a `_provenance` block naming which groups came from the log
and which were authored, rather than that distinction living only in a
README paragraph a reader might not reach.
"""

from __future__ import annotations

from enum import StrEnum


class Provenance(StrEnum):
    """How a field group's value was obtained."""

    LOG_DERIVED = "log-derived"
    """Read directly from the BPIC 2019 event log, or computed deterministically
    from fields that were."""

    AUTHORED = "authored"
    """Invented for this project because the log carries no corresponding
    signal. Per docs/DERIVATION.md 1.10, this currently applies only to the
    per-document monetary split on multi-GR / multi-invoice cases, and (in
    Session 2+) to quantities, dispositions, and free-text notes."""

    SURROGATE = "surrogate"
    """A structurally-required value with no real-world referent (e.g. a
    Plant code where SAP requires one to exist but the log carries none) --
    distinct from AUTHORED because it is not standing in for something we
    have any evidence about, only filling a schema slot."""

    NULL = "null"
    """Left unset because the log carries no signal and Session 1 declines to
    invent one. See docs/DERIVATION.md 3.1 -- quantities and Material/Plant/
    StorageLocation are NULL in Session 1."""


# Field groups as used across the rendered document, matching
# docs/DERIVATION.md section 3.1 exactly. Downstream code should reference
# these constants rather than re-typing the group names as string literals.
FIELD_GROUP_PO_IDENTITY = "po_identity_and_classification"
FIELD_GROUP_MATCH_FLAGS = "match_flags"
FIELD_GROUP_DOCUMENT_META = "document_counts_ordering_timestamps_users"
FIELD_GROUP_PO_ITEM_AMOUNT = "po_item_net_amount"
FIELD_GROUP_DOCUMENT_AMOUNT = "per_document_monetary_amount"
FIELD_GROUP_QUANTITY = "quantity_and_unit"
FIELD_GROUP_LOGISTICS = "material_plant_storage_location"
FIELD_GROUP_CURRENCY = "currency"

# The default provenance for each group, per docs/DERIVATION.md 3.1. Where a
# group's provenance is conditional (per-document amounts depend on whether
# the case has one document or many), render.py resolves it per case rather
# than reading this table -- this dict documents the *default*/*single-doc*
# case only.
DEFAULT_GROUP_PROVENANCE: dict[str, Provenance] = {
    FIELD_GROUP_PO_IDENTITY: Provenance.LOG_DERIVED,
    FIELD_GROUP_MATCH_FLAGS: Provenance.LOG_DERIVED,
    FIELD_GROUP_DOCUMENT_META: Provenance.LOG_DERIVED,
    FIELD_GROUP_PO_ITEM_AMOUNT: Provenance.LOG_DERIVED,
    # Overridden to AUTHORED for multi-document cases -- see render.py.
    FIELD_GROUP_DOCUMENT_AMOUNT: Provenance.LOG_DERIVED,
    FIELD_GROUP_QUANTITY: Provenance.NULL,
    FIELD_GROUP_LOGISTICS: Provenance.NULL,
    FIELD_GROUP_CURRENCY: Provenance.LOG_DERIVED,
}
