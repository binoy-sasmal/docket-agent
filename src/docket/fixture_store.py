"""Read access to the frozen case selection and rendered document fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from docket.schema.procurement import RenderedLineItem

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FROZEN_SELECTION_PATH = REPO_ROOT / "fixtures" / "frozen" / "selection" / "cases.json"
DEFAULT_RENDERED_DOCUMENTS_DIR = REPO_ROOT / "fixtures" / "rendered" / "documents"


class FixtureLookupError(LookupError):
    """Raised when a requested frozen fixture document cannot be loaded."""


class FrozenFixtureStore:
    """Load rendered documents for cases admitted by the frozen selection.

    The freeze pins *which* cases are in scope; the rendered document tier
    stores the SAP-shaped JSON for those cases. This store deliberately has no
    writer methods.
    """

    def __init__(
        self,
        *,
        selection_path: Path = DEFAULT_FROZEN_SELECTION_PATH,
        documents_dir: Path = DEFAULT_RENDERED_DOCUMENTS_DIR,
    ) -> None:
        self._selection_path = selection_path
        self._documents_dir = documents_dir
        self._selected_case_ids = self._load_selected_case_ids(selection_path)

    @property
    def selected_case_ids(self) -> tuple[str, ...]:
        """Case IDs fixed by `fixtures/frozen/selection/cases.json`."""
        return self._selected_case_ids

    def load_case(self, case_id: str) -> RenderedLineItem:
        """Load one frozen-selected rendered document by case ID."""
        if case_id not in self._selected_case_ids:
            raise FixtureLookupError(f"case {case_id!r} is not in the frozen selection")

        path = self._documents_dir / f"{case_id}.json"
        if not path.exists():
            raise FixtureLookupError(
                f"case {case_id!r} is frozen-selected but has no rendered document at {path}"
            )
        return RenderedLineItem.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _load_selected_case_ids(selection_path: Path) -> tuple[str, ...]:
        if not selection_path.exists():
            raise FixtureLookupError(
                f"frozen selection file does not exist at {selection_path}; "
                "run the freeze gate first"
            )

        data: Any = json.loads(selection_path.read_text(encoding="utf-8"))
        case_ids = data.get("selected_case_ids")
        if not isinstance(case_ids, list) or not all(isinstance(item, str) for item in case_ids):
            raise FixtureLookupError(
                f"{selection_path} must contain a list field named 'selected_case_ids'"
            )
        return tuple(case_ids)
