# SPDX-License-Identifier: Apache-2.0
"""Reference-resolver sample: batches, targeted negatives, labels, scoring (M1.3, 06 §2.9)."""

import pytest

from pdp_eval.refsample import (
    RefItem,
    build_sample,
    proposal,
    score,
    sentences,
    wilson,
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


@pytest.mark.parametrize(
    ("k", "n", "low", "high"),
    [(5, 6, 0.4365, 0.9699), (10, 10, 0.7225, 1.0), (0, 4, 0.0, 0.4899)],
)
def test_wilson_interval(k: int, n: int, low: float, high: float) -> None:
    lo, hi = wilson(k, n)  # type: ignore[misc]
    assert (round(lo, 4), round(hi, 4)) == (low, high)


def test_wilson_without_trials_is_none() -> None:
    assert wilson(0, 0) is None


SAMPLE = {"first": 4, "per_type": 1, "targeted": 1, "random_negatives": 1, "seed": 7}


def test_every_mention_is_an_item_stratified_batch_first(
    units: list[Unit], mentions: list[Mention]
) -> None:
    items = build_sample(units, mentions, **SAMPLE)  # type: ignore[arg-type]
    assert [(i.item_id, i.batch) for i in items] == [
        ("r-0001", "stratified"),
        ("r-0002", "stratified"),
        ("r-0003", "stratified"),
        ("r-0004", "stratified"),
        ("r-0005", "rest"),
        ("r-0006", "targeted"),
        ("r-0007", "random"),
    ]
    mention_items = [i for i in items if i.kind == "mention"]
    assert sorted((i.unit_id, i.start) for i in mention_items) == sorted(
        (m.unit_id, m.start) for m in mentions
    )
    assert {"self", "delegation", "range", "relative"} <= {t for i in items[:4] for t in i.patterns}
    for i in mention_items:
        unit = next(u for u in units if u.unit_id == i.unit_id)
        assert unit.text[i.start : i.end] == i.text
        assert f"[[{i.text}]]" in i.context
        assert i.proposed
        assert i.verdict is None
    assert build_sample(units, mentions, **SAMPLE) == items  # type: ignore[arg-type]


def test_targeted_negative_marks_uncovered_triggers(
    units: list[Unit], mentions: list[Mention]
) -> None:
    items = build_sample(units, mentions, **SAMPLE)  # type: ignore[arg-type]
    targeted, random_ = items[5], items[6]
    assert targeted.text == "Sanksi itu sesuai dengan ketentuan peraturan perundang-undangan."
    assert [t[2] for t in targeted.triggers] == ["ketentuan", "peraturan"]
    assert targeted.patterns == ["ketentuan", "peraturan"]
    assert "[[ketentuan]] [[peraturan]]" in targeted.context
    assert random_.triggers == []
    assert random_.text in (
        "Pengendali wajib menjaga data dengan cara yang aman dan patut.",
        "Penjelasan umum ini menguraikan latar belakang dan tujuan pengaturan secara lengkap.",
    )


def test_targeted_negatives_are_capped_and_stratified(
    units: list[Unit], mentions: list[Mention]
) -> None:
    both = build_sample(units, mentions, **(SAMPLE | {"targeted": 5}))  # type: ignore[arg-type]
    targeted = [i for i in both if i.batch == "targeted"]
    # the Pasal 2(2) sentence has an uncovered "Ketentuan" before its mention
    assert [i.unit_id for i in targeted] == ["s/p2/a2", "s/p3"]


def _item(**kw: object) -> RefItem:
    base: dict[str, object] = {
        "schema_version": 1,
        "item_id": "r-0001",
        "kind": "mention",
        "batch": "stratified",
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
        ({"batch": "targeted"}, "batch"),
    ],
)
def test_label_consistency(kw: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _item(**kw)


def test_score_rows(mentions: list[Mention]) -> None:
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
            batch="targeted",
            unit_id="s/p2/a2",
            start=0,
            end=82,
            text="Ketentuan sebagaimana dimaksud pada ayat (1) diatur dalam Peraturan Pemerintah.",
            patterns=["ketentuan"],
            triggers=[(0, 9, "ketentuan")],
            proposed=[],
            verdict="missed",
            annotator="faqih",
            gold_targets=["EXTERNAL"],
        ),
        _item(item_id="r-0004", verdict=None),
    ]
    rows = score(items, mentions)
    # the targeted negative overlaps the Pasal 2(2) mentions, but only its trigger span counts
    assert rows["overall"] == {
        "items": 3,
        "exact": 1,
        "tp": 3,
        "fp": 0,
        "fn": 2,
        "precision": 1.0,
        "recall": 0.6,
    }
    assert rows["mentions"]["fn"] == 1
    assert rows["relative"]["recall"] == 0.5
    assert rows["sebagaimana"] == rows["relative"]  # overlapping slices, same item
    assert rows["negatives:targeted"]["fn"] == 1
    assert rows["negatives:targeted"]["precision"] is None
    assert "negatives:random" not in rows
