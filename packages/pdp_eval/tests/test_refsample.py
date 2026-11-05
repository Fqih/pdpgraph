# SPDX-License-Identifier: Apache-2.0
"""Reference-resolver sample: strata, negatives, labels, scoring (M1.3, 06 §2.9)."""

import pytest

from pdp_eval.refsample import (
    RefItem,
    build_sample,
    proposal,
    score,
    sentences,
)
from pdp_ingest.refs import Mention, extract_refs
from pdp_ingest.segment import Unit


@pytest.fixture
def units(ref_units: list[Unit]) -> list[Unit]:
    return ref_units


@pytest.fixture
def mentions(units: list[Unit]) -> list[Mention]:
    return extract_refs(units)


def test_proposal_uses_pseudo_targets(mentions: list[Mention]) -> None:
    assert [proposal(m) for m in mentions] == [
        ["SELF"],
        ["s/p1"],
        ["s/p2/a1"],
        ["DELEGATION"],
        ["s/p1", "s/p2"],
    ]


def test_sentences_split_on_terminal_punctuation_only() -> None:
    text = "Denda Rp5.000.000,00 dibayar. Lalu: ini; itu"
    assert [text[a:b] for a, b in sentences(text)] == [
        "Denda Rp5.000.000,00 dibayar.",
        "Lalu:",
        "ini;",
        "itu",
    ]


def test_sample_strata_negatives_and_ids(units: list[Unit], mentions: list[Mention]) -> None:
    items = build_sample(units, mentions, size=4, per_type=1, negatives=2, seed=7)
    kinds = [i.kind for i in items]
    assert kinds == ["mention"] * 4 + ["negative"] * 2
    assert [i.item_id for i in items] == [f"r-{n:04d}" for n in range(1, 7)]
    tags = {t for i in items for t in i.patterns}
    assert {"self", "delegation", "range", "absolute", "relative"} <= tags
    for i in items[:4]:
        unit = next(u for u in units if u.unit_id == i.unit_id)
        assert unit.text[i.start : i.end] == i.text
        assert f"[[{i.text}]]" in i.context
        assert i.proposed
        assert i.proposed_by == "claude"
        assert i.verdict is None
    for i in items[4:]:
        assert i.proposed == []
        assert len(i.text.split()) >= 6
        assert not any(
            m.unit_id == i.unit_id and m.start < i.end and i.start < m.end for m in mentions
        )
    again = build_sample(units, mentions, size=4, per_type=1, negatives=2, seed=7)
    assert again == items


def _item(**kw: object) -> RefItem:
    base: dict[str, object] = {
        "schema_version": 1,
        "item_id": "r-0001",
        "kind": "mention",
        "unit_id": "s/p3",
        "label": "Pasal 3",
        "start": 12,
        "end": 41,
        "text": "Pasal 1 sampai dengan Pasal 2",
        "context": "x",
        "patterns": ["absolute", "range"],
        "proposed": ["s/p1", "s/p2"],
        "proposed_by": "claude",
    }
    return RefItem.model_validate(base | kw)


@pytest.mark.parametrize(
    ("kw", "message"),
    [
        ({"verdict": "correct"}, "annotator"),
        ({"verdict": "correct", "annotator": "faqih", "gold_targets": ["s/p1"]}, "equal"),
        ({"verdict": "wrong", "annotator": "faqih"}, "gold"),
        ({"verdict": "not_reference", "annotator": "faqih", "gold_targets": ["s/p1"]}, "empty"),
        ({"verdict": "missed", "annotator": "faqih", "gold_targets": ["s/p1"]}, "negative"),
        ({"gold_targets": ["s/p1"]}, "unlabeled"),
    ],
)
def test_label_consistency(kw: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _item(**kw)


def test_score_per_pattern_against_current_mentions(mentions: list[Mention]) -> None:
    items = [
        _item(verdict="correct", annotator="faqih", gold_targets=["s/p1", "s/p2"]),
        _item(
            item_id="r-0002",
            unit_id="s/p2/a2",
            start=10,
            end=44,
            text="sebagaimana dimaksud pada ayat (1)",
            patterns=["sebagaimana", "relative"],
            proposed=["s/p2/a1"],
            verdict="wrong",
            annotator="faqih",
            gold_targets=["s/p2/a1", "s/p2/a2"],
        ),
        _item(
            item_id="r-0003",
            kind="negative",
            unit_id="s/p1",
            start=0,
            end=62,
            text="Pengendali wajib menjaga data dengan cara yang aman dan patut.",
            patterns=[],
            proposed=[],
            verdict="missed",
            annotator="faqih",
            gold_targets=["s/p9"],
        ),
        _item(item_id="r-0004", verdict=None),
    ]
    rows = score(items, mentions)
    assert rows["overall"] == {
        "items": 3,
        "exact": 1,
        "tp": 3,
        "fp": 0,
        "fn": 2,
        "precision": 1.0,
        "recall": 0.6,
    }
    assert rows["range"]["recall"] == 1.0
    assert rows["relative"] == {
        "items": 1,
        "exact": 0,
        "tp": 1,
        "fp": 0,
        "fn": 1,
        "precision": 1.0,
        "recall": 0.5,
    }
    assert rows["negatives"]["fn"] == 1
    assert rows["negatives"]["precision"] is None  # nothing proposed
