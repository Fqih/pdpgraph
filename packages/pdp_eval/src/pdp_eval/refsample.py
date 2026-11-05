# SPDX-License-Identifier: Apache-2.0
"""Reference-resolver evaluation set (M1.3, 06 §2.9): `evals/datasets/pdp-refs/`.

Every mention of the source is an item. The first `first` items are a stratified batch (at
least `per_type` per pattern type where the source has that many) so per-pattern numbers exist
early; the remaining mentions follow in document order. Negatives catch missed references:
`targeted` sentences with a trigger token (Pasal, ayat, huruf, sebagaimana, Undang-Undang,
Peraturan, ketentuan) that no mention covers, stratified by trigger when there are more, plus
`random_negatives` random sentences with no trigger and no mention. The owner labels each item;
Claude proposes the set but writes no labels.

Gold is stored independently of the resolver (`gold_targets`), so `score` re-evaluates the
current resolver on the labeled spans: target-level TP/FP/FN, where SELF, EXTERNAL and DELEGATION
stand in as targets for mentions without an internal unit.
"""

import json
import math
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
TRIGGERS = ("pasal", "ayat", "huruf", "sebagaimana", "undang-undang", "peraturan", "ketentuan")
_TRIGGER = re.compile(r"\b(" + "|".join(TRIGGERS) + r")\b", re.IGNORECASE)
_BATCHES = {"mention": ("stratified", "rest"), "negative": ("targeted", "random")}
Z95 = 1.959964


class RefItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    item_id: str = Field(pattern=r"^r-\d{4}$")
    kind: Literal["mention", "negative"]
    batch: Literal["stratified", "rest", "targeted", "random"]
    unit_id: str
    label: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str = Field(min_length=1)
    context: str
    patterns: list[str] = []  # pattern types of a mention, trigger tokens of a negative
    triggers: list[tuple[int, int, str]] = []  # uncovered trigger tokens (targeted negatives)
    proposed: list[str] = []  # resolver proposal when sampled (shown to the annotator)
    proposed_by: Literal["claude"] = "claude"
    verdict: Literal["correct", "wrong", "not_reference", "no_reference", "missed"] | None = None
    gold_targets: list[str] = []
    annotator: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.batch not in _BATCHES[self.kind]:
            raise ValueError(f"{self.kind} items take batch {_BATCHES[self.kind]}")
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


def _context(text: str, start: int, end: int, marks: list[tuple[int, int]] | None = None) -> str:
    """The sentence(s) around [start, end) with each marked span in [[...]]."""
    spans = [s for s in sentences(text) if s[0] < end and start < s[1]] or [(start, end)]
    lo, hi = spans[0][0], spans[-1][1]
    out, pos = [], lo
    for a, b in marks if marks is not None else [(start, end)]:
        out += [text[pos:a], f"[[{text[a:b]}]]"]
        pos = b
    return "".join([*out, text[pos:hi]])


def stratified(
    tags: list[tuple[str, ...]],
    order: tuple[str, ...],
    size: int,
    per_type: int,
    rng: random.Random,
) -> list[int]:
    """Indices: at least `per_type` per tag (rarest tag first) where available, then random."""
    chosen: list[int] = []
    population = {t: [i for i, ts in enumerate(tags) if t in ts] for t in order}
    for tag in sorted(order, key=lambda t: (len(population[t]), order.index(t))):
        have = sum(1 for i in chosen if tag in tags[i])
        pool = [i for i in population[tag] if i not in chosen]
        chosen += rng.sample(pool, min(max(0, per_type - have), len(pool), size - len(chosen)))
    rest = [i for i in range(len(tags)) if i not in chosen]
    chosen += rng.sample(rest, min(len(rest), size - len(chosen)))
    return sorted(chosen)


def _covered(spans: list[tuple[int, int]], a: int, b: int) -> bool:
    return any(a < e and s < b for s, e in spans)


Hit = tuple[Unit, int, int, list[tuple[int, int, str]]]


def negative_pools(
    units: list[Unit], mentions: list[Mention]
) -> tuple[list[Hit], list[tuple[Unit, int, int]]]:
    """(sentences with trigger tokens no mention covers, with those tokens; sentences of at least
    MIN_NEGATIVE_WORDS words with no trigger and no mention). Repeated sentences count once."""
    spans: dict[str, list[tuple[int, int]]] = {}
    for m in mentions:
        spans.setdefault(m.unit_id, []).append((m.start, m.end))
    hits: list[Hit] = []
    plain: list[tuple[Unit, int, int]] = []
    seen: set[str] = set()
    for u in units:
        busy = spans.get(u.unit_id, [])
        for a, b in sentences(u.text):
            sentence = u.text[a:b]
            if sentence in seen:
                continue
            seen.add(sentence)
            found = list(_TRIGGER.finditer(u.text, a, b))
            free = [
                (t.start(), t.end(), t.group(1).lower())
                for t in found
                if not _covered(busy, t.start(), t.end())
            ]
            if free:
                hits.append((u, a, b, free))
            elif (
                not found
                and not _covered(busy, a, b)
                and len(sentence.split()) >= MIN_NEGATIVE_WORDS
            ):
                plain.append((u, a, b))
    return hits, plain


def build_sample(
    units: list[Unit],
    mentions: list[Mention],
    *,
    first: int = 50,
    per_type: int = 5,
    targeted: int = 40,
    random_negatives: int = 10,
    seed: int = 20261105,
) -> list[RefItem]:
    rng = random.Random(seed)  # noqa: S311 - reproducible sampling, not security
    by_id = {u.unit_id: u for u in units}
    items: list[RefItem] = []

    def add(**fields: object) -> None:
        items.append(
            RefItem.model_validate(
                {"schema_version": 1, "item_id": f"r-{len(items) + 1:04d}"} | fields
            )
        )

    batch1 = stratified([m.patterns for m in mentions], PATTERNS, first, per_type, rng)
    order = batch1 + [i for i in range(len(mentions)) if i not in batch1]
    for i in order:
        m, unit = mentions[i], by_id[mentions[i].unit_id]
        add(
            kind="mention",
            batch="stratified" if i in batch1 else "rest",
            unit_id=m.unit_id,
            label=unit.label,
            start=m.start,
            end=m.end,
            text=m.text,
            context=_context(unit.text, m.start, m.end),
            patterns=list(m.patterns),
            proposed=proposal(m),
        )
    hits, plain = negative_pools(units, mentions)
    tags = [tuple(dict.fromkeys(t[2] for t in free)) for *_, free in hits]
    present = tuple(t for t in TRIGGERS if any(t in ts for ts in tags))
    quota = math.ceil(targeted / len(present)) if present else 0
    for i in stratified(tags, present, targeted, quota, rng):
        u, a, b, free = hits[i]
        add(
            kind="negative",
            batch="targeted",
            unit_id=u.unit_id,
            label=u.label,
            start=a,
            end=b,
            text=u.text[a:b],
            context=_context(u.text, a, b, [(s, e) for s, e, _ in free]),
            patterns=list(tags[i]),
            triggers=free,
        )
    for u, a, b in sorted(
        rng.sample(plain, min(random_negatives, len(plain))), key=lambda c: (c[0].order, c[1])
    ):
        add(
            kind="negative",
            batch="random",
            unit_id=u.unit_id,
            label=u.label,
            start=a,
            end=b,
            text=u.text[a:b],
            context=u.text[a:b],
        )
    return items


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Wilson score interval for k successes in n trials (None without trials)."""
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def score(
    items: list[RefItem], mentions: list[Mention]
) -> dict[str, dict[str, int | float | None]]:
    """Rows over labeled items for the current mentions: `overall` (each item once, the
    headline), `mentions` (unique mentions), one overlapping slice per pattern type, and
    `negatives:targeted` / `negatives:random`. A targeted negative only counts mentions that
    overlap its trigger tokens, so another mention in the same sentence does not leak in."""
    by_unit: dict[str, list[Mention]] = {}
    for m in mentions:
        by_unit.setdefault(m.unit_id, []).append(m)
    rows: dict[str, dict[str, int]] = {}
    for item in items:
        if item.verdict is None:
            continue
        probes = [(s, e) for s, e, _ in item.triggers] or [(item.start, item.end)]
        found = {
            t
            for m in by_unit.get(item.unit_id, [])
            if _covered(probes, m.start, m.end)
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
        slices = (
            ["mentions", *item.patterns] if item.kind == "mention" else [f"negatives:{item.batch}"]
        )
        for key in ["overall", *slices]:
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
