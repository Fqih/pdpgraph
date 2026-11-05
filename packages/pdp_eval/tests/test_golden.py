# SPDX-License-Identifier: Apache-2.0
"""`pdp-golden` item schema (06 §2.1, M1.7). Fixtures are synthetic; labels here are test data."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pdp_eval.golden import GoldenItem, composition, dump_items, load_items


def _candidate(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": 1,
        "item_id": "g-0001",
        "question": "Apa yang dimaksud dengan Data Pribadi?",
        "language": "id",
        "as_of": "2026-11-05",
        "category": "definition",
        "hops": 1,
        "proposed_by": "claude",
    }
    return base | overrides


def _labeled(**overrides: Any) -> dict[str, Any]:
    return (
        _candidate(
            gold_verdict="INFORMATIONAL",
            gold_unit_ids=["uu27-2022/p1/n1"],
            acceptable_unit_ids=["uu27-2022/p1"],
            gold_answer_points=["test point"],
            annotator="faqih",
        )
        | overrides
    )


def test_unlabeled_candidate_is_valid_and_not_labeled() -> None:
    item = GoldenItem.model_validate(_candidate())
    assert not item.is_labeled
    assert item.gold_unit_ids == []
    assert item.annotator is None


def test_labeled_item_is_valid() -> None:
    item = GoldenItem.model_validate(_labeled())
    assert item.is_labeled
    assert item.proposed_by == "claude"


def test_proposed_by_is_optional() -> None:
    data = _candidate()
    del data["proposed_by"]
    assert GoldenItem.model_validate(data).proposed_by is None


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (_candidate(gold_unit_ids=["uu27-2022/p1"]), "unlabeled item must not carry gold"),
        (_candidate(gold_answer_points=["x"]), "unlabeled item must not carry gold"),
        (_candidate(annotator="faqih"), "unlabeled item must not carry gold"),
        (_labeled(annotator=None), "annotator"),
        (_labeled(gold_answer_points=[]), "answer point"),
        (_labeled(gold_unit_ids=[]), "gold unit"),
        (_labeled(gold_unit_ids=["uu27-2022/p1@1"]), "version"),
        (_labeled(gold_unit_ids=["uu27-2022/P1"]), "invalid"),
        (_labeled(gold_unit_ids=["uu27-2022/def/data-pribadi"]), "Pasal-path"),
        (_labeled(acceptable_unit_ids=["uu27-2022/bab1"]), "Pasal-path"),
        (_labeled(category="unanswerable"), "INSUFFICIENT_EVIDENCE"),
        (_candidate(category="multi_hop", hops=1), "hops"),
        (_candidate(item_id="g-1"), "item_id"),
        (_candidate(schema_version=2), "schema_version"),
        (_candidate(language="jv"), "language"),
        (_candidate(proposed_by="gpt"), "proposed_by"),
        (_candidate(extra=1), "extra"),
    ],
)
def test_invalid_items_rejected(data: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        GoldenItem.model_validate(data)


def test_unanswerable_with_no_units() -> None:
    item = GoldenItem.model_validate(
        _labeled(category="unanswerable", gold_verdict="INSUFFICIENT_EVIDENCE", gold_unit_ids=[])
    )
    assert item.is_labeled


def test_penjelasan_and_pj_umum_units_allowed() -> None:
    ids = ["uu27-2022/p46/a1#pj", "uu27-2022/pj-umum"]
    assert GoldenItem.model_validate(_labeled(gold_unit_ids=ids)).gold_unit_ids == ids


def test_load_and_dump_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "dev.jsonl"
    items = [
        GoldenItem.model_validate(_candidate()),
        GoldenItem.model_validate(_labeled(item_id="g-0002")),
    ]
    dump_items(path, items)
    assert load_items(path) == items
    first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert first["schema_version"] == 1
    assert first["gold_verdict"] is None


def test_duplicate_item_ids_rejected(tmp_path: Path) -> None:
    path = tmp_path / "dev.jsonl"
    line = json.dumps(_candidate())
    path.write_text(f"{line}\n{line}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate item_id g-0001"):
        load_items(path)


def test_invalid_line_reports_line_number(tmp_path: Path) -> None:
    path = tmp_path / "dev.jsonl"
    path.write_text(json.dumps(_candidate()) + "\n" + json.dumps(_candidate(hops=0)) + "\n")
    with pytest.raises(ValueError, match=r"dev\.jsonl:2"):
        load_items(path)


def test_composition_counts() -> None:
    items = [
        GoldenItem.model_validate(_candidate()),
        GoldenItem.model_validate(_candidate(item_id="g-0002", category="multi_hop", hops=2)),
        GoldenItem.model_validate(_candidate(item_id="g-0003", category="unanswerable")),
        GoldenItem.model_validate(_labeled(item_id="g-0004", language="en")),
    ]
    report = composition(items)
    assert report["items"] == 4
    assert report["labeled"] == 1
    assert report["by_category"]["definition"] == 2
    assert report["multi_hop_pct"] == 25.0
    assert report["unanswerable_pct"] == 25.0
    assert report["english_pct"] == 25.0
