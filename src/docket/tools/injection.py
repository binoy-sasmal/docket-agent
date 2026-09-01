"""Eval-only injection overlays for untrusted free-text fields.

fixtures/frozen/ and fixtures/rendered/ carry no note text -- BPIC 2019 has
none to derive from (docs/PROJECT.md 4.2), and both directories are Tier 1
(AGENTS.md): never edited to inject anything.

An overlay is applied to an in-memory copy of a rendered document at
`ReadOnlyODataTools` construction time. Nothing on disk changes. This is the
mechanism `evals/golden/injection_overlays.json` describes as
"do not edit frozen fixtures to apply these."
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from docket.schema.procurement import RenderedLineItem

OverlayTarget = Literal[
    "purchase_order_item_note",
    "goods_receipt_note",
    "supplier_invoice_note",
]


class OverlayNotAuthored(RuntimeError):
    """Raised when a held-out overlay is used before its payload is written.

    Held-out payloads are placeholders (`payload_status:
    "to_be_authored_repo_blind_before_final_run"`) until authored in a
    separate, repo-blind session per docs/PROJECT.md 6.1. Using one before
    then would defeat the point of holding it out.
    """


@dataclass(frozen=True)
class InjectionOverlay:
    overlay_id: str
    case_id: str
    target: OverlayTarget
    payload: str


def apply_overlay(document: RenderedLineItem, overlay: InjectionOverlay) -> RenderedLineItem:
    """Return a copy of `document` with the overlay's payload attached.

    A goods-receipt or invoice overlay with nothing to attach to (the case
    has zero of that document class) is a no-op -- there is no field to
    carry the payload, and fabricating an entry to hold it would misrepresent
    the fixture.
    """
    if overlay.target == "purchase_order_item_note":
        return document.model_copy(
            update={
                "purchase_order_item": document.purchase_order_item.model_copy(
                    update={"Note": overlay.payload}
                )
            }
        )
    if overlay.target == "goods_receipt_note":
        if not document.goods_receipts:
            return document
        updated_gr = document.goods_receipts[0].model_copy(update={"Note": overlay.payload})
        return document.model_copy(
            update={"goods_receipts": (updated_gr, *document.goods_receipts[1:])}
        )
    if overlay.target == "supplier_invoice_note":
        if not document.invoices:
            return document
        updated_invoice = document.invoices[0].model_copy(update={"Note": overlay.payload})
        return document.model_copy(update={"invoices": (updated_invoice, *document.invoices[1:])})
    raise ValueError(f"unknown overlay target {overlay.target!r}")


def apply_overlays(
    document: RenderedLineItem, overlays: tuple[InjectionOverlay, ...]
) -> RenderedLineItem:
    for overlay in overlays:
        if overlay.case_id == document.source_case_id:
            document = apply_overlay(document, overlay)
    return document


def load_public_overlays(path: Path) -> tuple[InjectionOverlay, ...]:
    """Load `public_overlays` from evals/golden/injection_overlays.json.

    Held-out overlays are deliberately not loaded by this function -- see
    `load_held_out_overlays`.
    """
    record = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        InjectionOverlay(
            overlay_id=entry["overlay_id"],
            case_id=entry["case_id"],
            target=entry["target"],
            payload=entry["payload"],
        )
        for entry in record["public_overlays"]
    )


def load_held_out_overlays(path: Path) -> tuple[InjectionOverlay, ...]:
    """Load `held_out_overlays`. Raises OverlayNotAuthored until each entry's
    placeholder `payload_status` has been replaced with a real `payload` by
    a separate, repo-blind authoring session (docs/PROJECT.md 6.1).
    """
    record = json.loads(path.read_text(encoding="utf-8"))
    overlays: list[InjectionOverlay] = []
    for entry in record["held_out_overlays"]:
        if "payload" not in entry:
            raise OverlayNotAuthored(
                f"{entry['overlay_id']} has no authored payload yet "
                f"(payload_status={entry.get('payload_status')!r})"
            )
        overlays.append(
            InjectionOverlay(
                overlay_id=entry["overlay_id"],
                case_id=entry["case_id"],
                target=entry["target"],
                payload=entry["payload"],
            )
        )
    return tuple(overlays)
