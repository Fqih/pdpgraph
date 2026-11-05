# SPDX-License-Identifier: Apache-2.0
"""`pdp-golden` item schema (06 §2.1) and JSONL I/O (M1.7).

An item is either an unlabeled candidate (every gold field empty, no annotator) or labeled
(`gold_verdict` set, plus annotator, answer points and gold units). Gold fields are written only
by the annotator through the labeling CLI; the schema refuses half-filled candidates.
"""

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from common import ids
from common.errors import InvalidIdError

# 04 §5.1 `Verdict`; kept in sync until pdp_core ships the query schemas (M1.8+).
Verdict = Literal[
    "OBLIGATION_APPLIES",
    "PROHIBITED",
    "PERMITTED",
    "NOT_APPLICABLE",
    "INFORMATIONAL",
    "INSUFFICIENT_EVIDENCE",
]
VERDICTS: tuple[Verdict, ...] = Verdict.__args__  # type: ignore[attr-defined]
Category = Literal[
    "definition",
    "obligation",
    "exception",
    "sanction",
    "procedure",
    "scope",
    "multi_hop",
    "temporal",
    "unanswerable",
]
CATEGORIES: tuple[Category, ...] = Category.__args__  # type: ignore[attr-defined]


def check_unit_id(value: str) -> str:
    """A gold unit is a version-free Pasal-path unit (Pasal/ayat/huruf/angka, `#pj`) or
    `pj-umum`; structure, definition and obligation ids are not gold units (GUIDELINE §2)."""
    try:
        parsed = ids.parse(value)
    except InvalidIdError as exc:
        raise ValueError(f"invalid unit id {value!r}: {exc}") from exc
    if isinstance(parsed, ids.NodeId):
        raise ValueError(f"{value!r}: gold units are version-free (drop the @version)")
    if not isinstance(parsed.path, ids.PasalPath | ids.PjUmum):
        raise ValueError(f"{value!r}: gold units must be Pasal-path units or pj-umum")
    return value


class GoldenItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    item_id: Annotated[str, StringConstraints(pattern=r"^g-\d{4}$")]
    question: str = Field(min_length=1)
    language: Literal["id", "en"]
    as_of: date
    category: Category
    hops: int = Field(ge=1)
    gold_verdict: Verdict | None = None
    gold_unit_ids: list[str] = []
    acceptable_unit_ids: list[str] = []
    gold_answer_points: list[Annotated[str, StringConstraints(min_length=1)]] = []
    annotator: str | None = None
    reviewed_by: str | None = None
    notes: str = ""
    proposed_by: Literal["claude", "faqih", "synthetic"] | None = None

    @field_validator("gold_unit_ids", "acceptable_unit_ids")
    @classmethod
    def _unit_ids(cls, values: list[str]) -> list[str]:
        return [check_unit_id(v) for v in values]

    @property
    def is_labeled(self) -> bool:
        return self.gold_verdict is not None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.category == "multi_hop" and self.hops < 2:
            raise ValueError("multi_hop items need hops >= 2")
        if not self.is_labeled:
            gold = (self.gold_unit_ids, self.acceptable_unit_ids, self.gold_answer_points)
            if any(gold) or self.annotator or self.reviewed_by:
                raise ValueError("unlabeled item must not carry gold fields or an annotator")
            return self
        if not self.annotator:
            raise ValueError("labeled item needs an annotator")
        if not self.gold_answer_points:
            raise ValueError("labeled item needs at least one answer point")
        if self.category == "unanswerable" and self.gold_verdict != "INSUFFICIENT_EVIDENCE":
            raise ValueError("unanswerable items are labeled INSUFFICIENT_EVIDENCE")
        if not self.gold_unit_ids and self.gold_verdict != "INSUFFICIENT_EVIDENCE":
            raise ValueError("labeled item needs at least one gold unit")
        return self


def load_items(path: Path) -> list[GoldenItem]:
    items: list[GoldenItem] = []
    seen: set[str] = set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = GoldenItem.model_validate(json.loads(line))
        except (ValidationError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path.name}:{n}: {exc}") from exc
        if item.item_id in seen:
            raise ValueError(f"{path.name}:{n}: duplicate item_id {item.item_id}")
        seen.add(item.item_id)
        items.append(item)
    return items


def dump_items(path: Path, items: list[GoldenItem]) -> None:
    lines = "".join(json.dumps(i.model_dump(mode="json"), ensure_ascii=False) + "\n" for i in items)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(lines, encoding="utf-8")
    tmp.replace(path)


def composition(items: list[GoldenItem]) -> dict[str, object]:
    """Counts against the 06 §2.1 composition targets."""
    n = len(items) or 1

    def pct(k: int) -> float:
        return round(100 * k / n, 1)

    return {
        "items": len(items),
        "labeled": sum(i.is_labeled for i in items),
        "by_category": dict(Counter(i.category for i in items)),
        "multi_hop_pct": pct(sum(i.hops >= 2 for i in items)),
        "unanswerable_pct": pct(sum(i.category == "unanswerable" for i in items)),
        "english_pct": pct(sum(i.language == "en" for i in items)),
        "temporal_pct": pct(sum(i.category == "temporal" for i in items)),
    }
