# SPDX-License-Identifier: Apache-2.0
"""Labeling CLI: label, drop, blind re-label, agreement (M1.7). Labels are synthetic test data."""

import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pdp_eval.cli import main
from pdp_eval.golden import GoldenItem, dump_items, load_items
from pdp_eval.law import LawText
from pdp_eval.retest import read_log

T0 = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)


def _item(item_id: str, **extra: object) -> GoldenItem:
    return GoldenItem.model_validate(
        {
            "schema_version": 1,
            "item_id": item_id,
            "question": f"Pertanyaan {item_id}?",
            "language": "id",
            "as_of": "2026-11-05",
            "category": "scope",
            "hops": 1,
            "proposed_by": "claude",
            "notes": "SECRET-NOTE",
        }
        | extra
    )


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    path = tmp_path / "v0" / "dev.jsonl"
    path.parent.mkdir()
    dump_items(path, [_item("g-0001"), _item("g-0002")])
    return path


def _run(
    argv: list[str], answers: list[str], law: LawText, now: datetime = T0
) -> tuple[int, str, list[str]]:
    prompts: list[str] = []
    feed: Iterator[str] = iter(answers)

    def ask(prompt: str) -> str:
        prompts.append(prompt)
        return next(feed)

    out = io.StringIO()
    code = main(argv, ask=ask, out=out, now=lambda: now, law=law)
    return code, out.getvalue(), prompts


LABEL_G1 = [
    ":show 2",  # law text on demand, then the same prompt again
    "5",  # INFORMATIONAL
    "uu27-2022/p9",  # unknown unit: re-asked
    "uu27-2022/p2/a2",
    "uu27-2022/p2",
    "",  # no answer point yet: re-asked
    "tidak berlaku untuk rumah tangga",
    "",
    "",  # keep hops
    "",  # keep as_of
    "cek penjelasan",
]


def test_label_writes_gold_only_from_input_and_logs_first_pass(dataset: Path, law: LawText) -> None:
    code, out, _ = _run(["label", "--file", str(dataset)], [*LABEL_G1, ":quit"], law)
    assert code == 0
    assert "uu27-2022/p2/a1/hb/n1" in out  # :show printed suggested ids
    assert "not a unit of the source" in out
    g1, g2 = load_items(dataset)
    assert g1.gold_verdict == "INFORMATIONAL"
    assert g1.gold_unit_ids == ["uu27-2022/p2/a2"]
    assert g1.acceptable_unit_ids == ["uu27-2022/p2"]
    assert g1.gold_answer_points == ["tidak berlaku untuk rumah tangga"]
    assert g1.annotator == "faqih"
    assert g1.notes == "SECRET-NOTE | faqih: cek penjelasan"
    assert not g2.is_labeled  # quit before g-0002
    (entry,) = read_log(dataset.parent / "annotation-log.jsonl")
    assert (entry.item_id, entry.phase, entry.at) == ("g-0001", "first", T0)


def test_invalid_hops_is_not_saved(dataset: Path, law: LawText) -> None:
    answers = ["5", "uu27-2022/p2/a2", "", "titik", "", "0", "", ""]
    _, out, _ = _run(["label", "--file", str(dataset), "--item", "g-0001"], answers, law)
    assert "not saved" in out
    assert not load_items(dataset)[0].is_labeled


def test_skip_leaves_item_untouched(dataset: Path, law: LawText) -> None:
    before = dataset.read_text()
    _run(["label", "--file", str(dataset)], ["", ""], law)
    assert dataset.read_text() == before
    assert not (dataset.parent / "annotation-log.jsonl").exists()


def test_drop_removes_item_after_confirmation(dataset: Path, law: LawText) -> None:
    _run(["label", "--file", str(dataset)], ["drop", "yes", ":quit"], law)
    assert [i.item_id for i in load_items(dataset)] == ["g-0002"]


def test_as_of_can_be_pinned_earlier(dataset: Path, law: LawText) -> None:
    answers = ["3", "uu27-2022/p1/n1", "", "boleh", "", "", "2025-01-01", ""]
    _run(["label", "--file", str(dataset), "--item", "g-0002"], answers, law)
    assert str(load_items(dataset)[1].as_of) == "2025-01-01"


def _label_all(dataset: Path, law: LawText) -> None:
    for item_id in ("g-0001", "g-0002"):
        answers = ["5", "uu27-2022/p2/a2", "", "titik", "", "", "", ""]
        _run(["label", "--file", str(dataset), "--item", item_id], answers, law)


def test_relabel_refuses_before_seven_days(dataset: Path, law: LawText) -> None:
    _label_all(dataset, law)
    code, out, _ = _run(
        ["relabel", "--file", str(dataset), "--sample", "2"], [], law, T0 + timedelta(days=6)
    )
    assert code == 1
    assert "only 0 items eligible" in out


def test_relabel_is_blind_and_agreement_is_intra_annotator(dataset: Path, law: LawText) -> None:
    _label_all(dataset, law)
    later = T0 + timedelta(days=7)
    answers = ["5", "uu27-2022/p2/a2", "1", "uu27-2022/p2/a2 uu27-2022/p2/a1"]
    argv = ["relabel", "--file", str(dataset), "--sample", "2", "--seed", "7"]
    code, out, prompts = _run(argv, answers, law, later)
    assert code == 0
    assert "SECRET-NOTE" not in out
    assert "INFORMATIONAL" not in out.replace("5=INFORMATIONAL", "")  # no earlier label shown
    assert "titik" not in out
    assert not any("acceptable" in p or "as_of" in p for p in prompts)
    log = read_log(dataset.parent / "annotation-log.jsonl")
    assert [e.phase for e in log] == ["first", "first", "retest", "retest"]
    assert all(e.seed == 7 for e in log[2:])

    code, out, _ = _run(["agreement", "--file", str(dataset)], [], law)
    report = json.loads(out)
    assert report["kind"].startswith("intra-annotator test-retest")
    assert report["items"] == 2
    assert report["verdict_agreement_pct"] == 50.0
    assert report["mean_gold_unit_jaccard"] == 0.75

    # Already retested items are not offered again.
    code, out, _ = _run(argv, [], law, later)
    assert "only 0 items eligible" in out


def test_validate_reports_composition_and_unknown_units(dataset: Path, law: LawText) -> None:
    code, out, _ = _run(["validate", "--file", str(dataset)], [], law)
    assert code == 0
    assert json.loads(out)["items"] == 2
    items = load_items(dataset)
    bad = items[0].model_copy(
        update={
            "gold_verdict": "INFORMATIONAL",
            "gold_unit_ids": ["uu27-2022/p2/a7"],
            "gold_answer_points": ["x"],
            "annotator": "faqih",
        }
    )
    dump_items(dataset, [bad, items[1]])
    code, out, _ = _run(["validate", "--file", str(dataset)], [], law)
    assert code == 1
    assert "g-0001: unknown unit uu27-2022/p2/a7" in out


def test_show_command(law: LawText) -> None:
    code, out, _ = _run(["show", "3"], [], law)
    assert code == 0
    assert "a. pelindungan;   [uu27-2022/p3/ha]" in out
    _, out, _ = _run(["show", "umum"], [], law)
    assert "Latar belakang." in out
