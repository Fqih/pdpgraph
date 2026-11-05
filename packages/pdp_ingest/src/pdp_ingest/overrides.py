# SPDX-License-Identifier: Apache-2.0
"""Manual text corrections, `data/overrides/<source_id>.yaml` (03 §5.1, M1.2).

Applied to the `segment` output, never by editing generated artifacts. An entry replaces one
exact occurrence of `find` in one unit's text. An entry whose `find` no longer occurs exactly
once is stale and fails the run, so a changed source cannot silently drop or misapply a fix.

Each entry names the reference PDF page that carries the correct wording. `confirmed_by` stays
empty until the owner checks the page image; unconfirmed entries are still applied and are
listed for review.
"""

from dataclasses import replace
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from pdp_ingest.segment import Unit


class OverrideError(Exception):
    """An override does not apply cleanly to the segmented units."""


class Override(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    unit_id: str = Field(min_length=1)
    find: str = Field(min_length=1)
    replace: str
    reason: str = Field(min_length=1)
    pdf_page: int = Field(ge=1)  # 1-based page of the reference PDF with the correct wording
    confirmed_by: str | None = None
    changes_meaning: bool = False  # reviewed first (crosscheck.md §1)


def load_overrides(path: Path) -> list[Override]:
    """Entries of an overrides file; a missing file means no overrides."""
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return TypeAdapter(list[Override]).validate_python(data)


def apply_overrides(units: list[Unit], overrides: list[Override]) -> list[Unit]:
    """New unit list with every override applied, in file order per unit."""
    texts = {u.unit_id: u.text for u in units}
    for o in overrides:
        if o.unit_id not in texts:
            raise OverrideError(f"override for missing unit {o.unit_id}")
        count = texts[o.unit_id].count(o.find)
        if count != 1:
            raise OverrideError(f"stale override on {o.unit_id}: {o.find!r} occurs {count} times")
        texts[o.unit_id] = texts[o.unit_id].replace(o.find, o.replace)
    return [replace(u, text=texts[u.unit_id]) if u.text != texts[u.unit_id] else u for u in units]


def counts(overrides: list[Override]) -> tuple[int, int]:
    """(overrides_total, overrides_unconfirmed); the v0.1 exit gate needs unconfirmed = 0."""
    return len(overrides), sum(not o.confirmed_by for o in overrides)
