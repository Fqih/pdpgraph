# SPDX-License-Identifier: Apache-2.0
"""Reference-resolver evaluation sample (M1.3, 06 §2.9): `evals/datasets/pdp-refs/`.

The sample holds `size` mentions, stratified so every pattern type gets at least `per_type`
items where the source has that many, plus `negatives` random sentences in which the resolver
found nothing (they catch missed references). The owner labels each item; Claude proposes the
sample but writes no labels.

Gold is stored independently of the resolver (`gold_targets`), so `score` re-evaluates the
current resolver on the labeled spans: target-level TP/FP/FN, where SELF, EXTERNAL and DELEGATION
stand in as targets for mentions without an internal unit.
"""

import json
import random
import re
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pdp_ingest.refs import Mention
from pdp_ingest.segment import Unit

PATTERNS = (
    "absolute",
    "relative",
    "list",
    "range",
    "sebagaimana",
    "self",
    "external",
    "delegation",
    "penjelasan",
)
PSEUDO_TARGETS = ("SELF", "EXTERNAL", "DELEGATION")
MENTION_VERDICTS = ("correct", "wrong", "not_reference")
NEGATIVE_VERDICTS = ("no_reference", "missed")
_SENTENCE = re.compile(r"[^\s].*?(?:[.;:](?=\s|$)|$)", re.DOTALL)
MIN_NEGATIVE_WORDS = 6


class RefItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    item_id: str = Field(pattern=r"^r-\d{4}$")
    kind: Literal["mention", "negative"]
    unit_id: str
    label: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str = Field(min_length=1)
    context: str
    patterns: list[str] = []
    proposed: list[str] = []  # resolver proposal when sampled (shown to the annotator)
    proposed_by: Literal["claude"] = "claude"
    verdict: Literal["correct", "wrong", "not_reference", "no_reference", "missed"] | None = None
    gold_targets: list[str] = []
    annotator: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.verdict is None:
            if self.gold_targets or self.annotator:
                raise ValueError("unlabeled item must not carry gold targets or an annotator")
            return self
        if not self.annotator:
            raise ValueError("labeled item needs an annotator")
        allowed = MENTION_VERDICTS if self.kind == "mention" else NEGATIVE_VERDICTS
        if self.verdict not in allowed:
            raise ValueError(f"{self.kind} items take {allowed}, not a negative/mention verdict")
        if self.verdict == "correct" and self.gold_targets != self.proposed:
            raise ValueError("'correct' means gold_targets equal the proposal")
        if self.verdict in ("wrong", "missed") and not self.gold_targets:
            raise ValueError(f"'{self.verdict}' needs gold targets")
        if self.verdict in ("not_reference", "no_reference") and self.gold_targets:
            raise ValueError(f"'{self.verdict}' means gold targets are empty")
        return self


def proposal(m: Mention) -> list[str]:
    if m.kind == "DELEGATION":
        return ["DELEGATION"]
    if m.resolution == "SELF":
        return ["SELF"]
    if m.resolution == "EXTERNAL_UNRESOLVED":
        return ["EXTERNAL"]
    return list(m.targets)


def sentences(text: str) -> list[tuple[int, int]]:
    """Sentence spans: split after '.', ';' or ':' followed by whitespace, and at line ends."""
    out = []
    for line in re.finditer(r"[^\n]+", text):
        out += [
            (line.start() + s.start(), line.start() + s.end())
            for s in _SENTENCE.finditer(line.group(0))
        ]
    return out


def _context(text: str, start: int, end: int) -> str:
    spans = [s for s in sentences(text) if s[0] < end and start < s[1]] or [(start, end)]
    lo, hi = spans[0][0], spans[-1][1]
    return f"{text[lo:start]}[[{text[start:end]}]]{text[end:hi]}"


def _stratified(mentions: list[Mention], size: int, per_type: int, rng: random.Random) -> list[int]:
    chosen: list[int] = []
    population = {p: [i for i, m in enumerate(mentions) if p in m.patterns] for p in PATTERNS}
    for pattern in sorted(PATTERNS, key=lambda p: (len(population[p]), PATTERNS.index(p))):
        have = sum(1 for i in chosen if pattern in mentions[i].patterns)
        pool = [i for i in population[pattern] if i not in chosen]
        chosen += rng.sample(pool, min(max(0, per_type - have), len(pool), size - len(chosen)))
    rest = [i for i in range(len(mentions)) if i not in chosen]
    chosen += rng.sample(rest, min(len(rest), size - len(chosen)))
    return sorted(chosen)


def build_sample(
    units: list[Unit],
    mentions: list[Mention],
    *,
    size: int = 50,
    per_type: int = 5,
    negatives: int = 20,
    seed: int = 20261105,
) -> list[RefItem]:
    rng = random.Random(seed)  # noqa: S311 - reproducible sampling, not security
    by_id = {u.unit_id: u for u in units}
    items: list[RefItem] = []
    for i in _stratified(mentions, size, per_type, rng):
        m = mentions[i]
        unit = by_id[m.unit_id]
        items.append(
            RefItem(
                schema_version=1,
                item_id=f"r-{len(items) + 1:04d}",
                kind="mention",
                unit_id=m.unit_id,
                label=unit.label,
                start=m.start,
                end=m.end,
                text=m.text,
                context=_context(unit.text, m.start, m.end),
                patterns=list(m.patterns),
                proposed=proposal(m),
            )
        )
    spans: dict[str, list[tuple[int, int]]] = {}
    for m in mentions:
        spans.setdefault(m.unit_id, []).append((m.start, m.end))
    candidates, seen = [], set()
    for u in units:
        for a, b in sentences(u.text):
            sentence = u.text[a:b]
            busy = any(a < e and s < b for s, e in spans.get(u.unit_id, []))
            if busy or len(sentence.split()) < MIN_NEGATIVE_WORDS or sentence in seen:
                continue
            seen.add(sentence)
            candidates.append((u, a, b))
    for u, a, b in sorted(
        rng.sample(candidates, min(negatives, len(candidates))), key=lambda c: (c[0].order, c[1])
    ):
        items.append(
            RefItem(
                schema_version=1,
                item_id=f"r-{len(items) + 1:04d}",
                kind="negative",
                unit_id=u.unit_id,
                label=u.label,
                start=a,
                end=b,
                text=u.text[a:b],
                context=u.text[a:b],
            )
        )
    return items


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def score(
    items: list[RefItem], mentions: list[Mention]
) -> dict[str, dict[str, int | float | None]]:
    """Per-pattern, negatives and overall rows over labeled items, for the current mentions."""
    by_unit: dict[str, list[Mention]] = {}
    for m in mentions:
        by_unit.setdefault(m.unit_id, []).append(m)
    rows: dict[str, dict[str, int]] = {}
    for item in items:
        if item.verdict is None:
            continue
        found = {
            t
            for m in by_unit.get(item.unit_id, [])
            if m.start < item.end and item.start < m.end
            for t in proposal(m)
        }
        gold = set(item.gold_targets)
        counts = {
            "items": 1,
            "exact": int(found == gold),
            "tp": len(found & gold),
            "fp": len(found - gold),
            "fn": len(gold - found),
        }
        keys = ["overall", *(item.patterns if item.kind == "mention" else ["negatives"])]
        for key in keys:
            row = rows.setdefault(key, dict.fromkeys(counts, 0))
            for k, v in counts.items():
                row[k] += v
    return {
        key: {
            **row,
            "precision": _ratio(row["tp"], row["tp"] + row["fp"]),
            "recall": _ratio(row["tp"], row["tp"] + row["fn"]),
        }
        for key, row in rows.items()
    }


def load_ref_items(path: Path) -> list[RefItem]:
    items = [
        RefItem.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len({i.item_id for i in items}) != len(items):
        raise ValueError(f"{path.name}: duplicate item_id")
    return items


def dump_ref_items(path: Path, items: list[RefItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        "".join(json.dumps(i.model_dump(mode="json"), ensure_ascii=False) + "\n" for i in items),
        encoding="utf-8",
    )
    tmp.replace(path)
