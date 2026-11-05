# SPDX-License-Identifier: Apache-2.0
"""Term-link evaluation set (M1.4, 06 §2.10): `evals/datasets/pdp-terms/`.

An item is one unit-term link from `pdp_ingest.defs.link_terms`: `defined` links (the
`USES_TERM` edges) and `informal` (lowercase) matches. The sample is stratified by term, rarest
first, so every term appears where the size allows. The owner marks each link correct or wrong;
for an informal match, correct means the text does use the defined term. Claude proposes the set
but writes no labels.

`score_terms` re-checks every labeled link against the current linker: a link it no longer
produces (same unit, term and kind) is counted as stale and left out of precision.
"""

import json
import random
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pdp_eval.refsample import sentences, stratified
from pdp_ingest.defs import Definition, TermUse
from pdp_ingest.segment import Unit

VERDICTS = ("correct", "wrong")


class TermItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    item_id: str = Field(pattern=r"^t-\d{4}$")
    kind: Literal["defined", "informal"]
    unit_id: str
    label: str
    node_id: str
    term: str
    spans: list[tuple[int, int]] = Field(min_length=1)
    context: str  # the sentences holding the spans, each span in [[...]]
    proposed_by: Literal["claude"] = "claude"
    verdict: Literal["correct", "wrong"] | None = None
    annotator: str | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.verdict is None and self.annotator:
            raise ValueError("unlabeled item must not carry an annotator")
        if self.verdict is not None and not self.annotator:
            raise ValueError("labeled item needs an annotator")
        return self


def _context(text: str, spans: list[tuple[int, int]]) -> str:
    parts = []
    for a, b in sentences(text):
        inside = [(s, e) for s, e in spans if a <= s < b]
        if not inside:
            continue
        out, pos = [], a
        for s, e in inside:
            out += [text[pos:s], f"[[{text[s:e]}]]"]
            pos = e
        parts.append("".join([*out, text[pos:b]]))
    return " … ".join(parts)


def build_term_sample(
    units: list[Unit],
    defs: list[Definition],
    uses: list[TermUse],
    *,
    defined: int = 30,
    informal: int = 10,
    seed: int = 20261105,
) -> list[TermItem]:
    """`defined` USES_TERM links and `informal` matches, each stratified by term."""
    rng = random.Random(seed)  # noqa: S311 - reproducible sampling, not crypto
    by_id = {u.unit_id: u for u in units}
    term = {d.node_id: d.term for d in defs}
    order = tuple(term)
    chosen: list[TermUse] = []
    for kind, size in (("defined", defined), ("informal", informal)):
        pool = [u for u in uses if u.kind == kind]
        tags: list[tuple[str, ...]] = [(u.node_id,) for u in pool]
        chosen += [
            pool[i] for i in stratified(tags, order, size, 2 if kind == "defined" else 1, rng)
        ]
    return [
        TermItem(
            schema_version=1,
            item_id=f"t-{n:04d}",
            kind=u.kind,
            unit_id=u.unit_id,
            label=by_id[u.unit_id].label,
            node_id=u.node_id,
            term=term[u.node_id],
            spans=list(u.spans),
            context=_context(by_id[u.unit_id].text, list(u.spans)),
        )
        for n, u in enumerate(chosen, start=1)
    ]


def score_terms(items: list[TermItem], uses: list[TermUse]) -> dict[str, dict[str, int]]:
    """Rows `defined`, `informal`, one `term:<term>` slice per term of defined links, `stale`."""
    current = {(u.unit_id, u.node_id, u.kind) for u in uses}
    rows: dict[str, dict[str, int]] = {}
    for item in items:
        if item.verdict is None:
            continue
        live = (item.unit_id, item.node_id, item.kind) in current
        keys = [item.kind, f"term:{item.term}"] if item.kind == "defined" else [item.kind]
        for key in keys if live else ["stale"]:
            row = rows.setdefault(key, {"items": 0, "correct": 0})
            row["items"] += 1
            row["correct"] += item.verdict == "correct"
    return rows


def load_term_items(path: Path) -> list[TermItem]:
    items = [
        TermItem.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len({i.item_id for i in items}) != len(items):
        raise ValueError(f"{path.name}: duplicate item_id")
    return items


def dump_term_items(path: Path, items: list[TermItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        "".join(json.dumps(i.model_dump(mode="json"), ensure_ascii=False) + "\n" for i in items),
        encoding="utf-8",
    )
    tmp.replace(path)
