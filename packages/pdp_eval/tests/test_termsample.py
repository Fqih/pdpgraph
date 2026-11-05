# SPDX-License-Identifier: Apache-2.0
"""Term-link sample: stratified build, validation, precision with Wilson intervals (M1.4)."""

from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from pdp_eval.termsample import (
    TermItem,
    build_term_sample,
    dump_term_items,
    load_term_items,
    score_terms,
)
from pdp_ingest.defs import TermUse, extract_definitions, link_terms
from pdp_ingest.refs import extract_refs
from pdp_ingest.segment import Unit


def _uses(units: list[Unit]) -> list[TermUse]:
    return link_terms(units, extract_definitions(units), extract_refs(units))


def _build(units: list[Unit], defined: int = 4, informal: int = 2) -> list[TermItem]:
    return build_term_sample(
        units, extract_definitions(units), _uses(units), defined=defined, informal=informal, seed=3
    )


def test_sample_sizes_kinds_and_term_coverage(term_units: list[Unit]) -> None:
    items = _build(term_units)
    assert Counter(i.kind for i in items) == {"defined": 4, "informal": 2}
    assert [i.item_id for i in items] == [f"t-{n:04d}" for n in range(1, 7)]
    terms = {i.term for i in items if i.kind == "defined"}
    assert terms == {"Data Pribadi", "Subjek Data Pribadi", "Korporasi"}
    assert all(i.proposed_by == "claude" and i.verdict is None for i in items)


def test_sample_takes_all_when_fewer(term_units: list[Unit]) -> None:
    items = _build(term_units, defined=100, informal=100)
    uses = _uses(term_units)
    assert len(items) == len(uses)


def test_context_marks_every_span(term_units: list[Unit]) -> None:
    items = _build(term_units, defined=100, informal=100)
    p3 = {i.kind: i for i in items if i.unit_id == "s/p3" and i.term == "Data Pribadi"}
    assert p3["defined"].context == (
        "Setiap korporasi menjaga data pribadi milik subjek [[Data Pribadi]]."
    )
    p3 = p3["informal"]
    assert p3.context == "Setiap korporasi menjaga [[data pribadi]] milik subjek Data Pribadi."
    (p2,) = [i for i in items if i.unit_id == "s/p2" and i.term == "Data Pribadi"]
    assert p2.context == "Korporasi memproses [[Data Pribadi]]."


def test_labels_are_validated(term_units: list[Unit]) -> None:
    item = _build(term_units)[0]
    with pytest.raises(ValidationError, match="annotator"):
        TermItem.model_validate(item.model_dump() | {"verdict": "correct"})
    with pytest.raises(ValidationError, match="unlabeled"):
        TermItem.model_validate(item.model_dump() | {"annotator": "faqih"})
    labeled = TermItem.model_validate(item.model_dump() | {"verdict": "wrong", "annotator": "x"})
    assert labeled.verdict == "wrong"


def test_roundtrip(tmp_path: Path, term_units: list[Unit]) -> None:
    items = _build(term_units)
    path = tmp_path / "s.jsonl"
    dump_term_items(path, items)
    assert load_term_items(path) == items


def test_score_rows_and_stale_links(term_units: list[Unit]) -> None:
    items = _build(term_units, defined=100, informal=100)
    verdicts = ["correct", "correct", "wrong", "correct", "correct", "wrong", "correct"]
    labeled = [
        TermItem.model_validate(i.model_dump() | {"verdict": v, "annotator": "x"})
        for i, v in zip(items, verdicts, strict=False)
    ]
    rows = score_terms(labeled, _uses(term_units))
    done = [i for i in labeled if i.verdict]
    defined = [i for i in done if i.kind == "defined"]
    assert rows["defined"]["items"] == len(defined)
    assert rows["defined"]["correct"] == sum(i.verdict == "correct" for i in defined)
    assert sum(rows[f"term:{t}"]["items"] for t in {i.term for i in defined}) == len(defined)
    # a link the current linker no longer produces is stale, not scored
    stale = score_terms(labeled, [])
    assert stale["stale"]["items"] == len(done)
    assert "defined" not in stale
