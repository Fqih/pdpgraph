# SPDX-License-Identifier: Apache-2.0
"""Reference sample CLI: build, label, report (M1.3). Labels here are synthetic test data."""

import io
from collections.abc import Iterator
from pathlib import Path

import pytest

from pdp_eval.cli import main
from pdp_eval.law import LawText
from pdp_eval.refsample import load_ref_items
from pdp_ingest.segment import Unit


@pytest.fixture
def law(ref_units: list[Unit]) -> LawText:
    return LawText("s", ref_units)


def _run(argv: list[str], answers: list[str], law: LawText) -> tuple[int, str, list[str]]:
    prompts: list[str] = []
    feed: Iterator[str] = iter(answers)

    def ask(prompt: str) -> str:
        prompts.append(prompt)
        return next(feed)

    out = io.StringIO()
    return main(argv, ask=ask, out=out, law=law), out.getvalue(), prompts


SAMPLE = [
    "--first",
    "4",
    "--per-type",
    "1",
    "--targeted",
    "1",
    "--random-negatives",
    "1",
    "--seed",
    "7",
]


def test_sample_is_written_once(tmp_path: Path, law: LawText) -> None:
    path = tmp_path / "pdp-refs" / "v0" / "sample.jsonl"
    code, out, _ = _run(["refs-sample", "--file", str(path), *SAMPLE], [], law)
    assert code == 0
    assert [i.batch for i in load_ref_items(path)] == ["stratified"] * 4 + [
        "rest",
        "targeted",
        "random",
    ]
    assert "range: 1 of 1 in the first batch" in out
    assert "targeted negatives: 1 of 2 candidates" in out
    code, out, _ = _run(["refs-sample", "--file", str(path), *SAMPLE], [], law)
    assert code == 1
    assert "exists" in out


def test_label_then_report(tmp_path: Path, law: LawText) -> None:
    path = tmp_path / "sample.jsonl"
    _run(["refs-sample", "--file", str(path), *SAMPLE], [], law)
    answers = [
        "c",
        "",  # r-0001 SELF
        "w",
        "p9",
        "+p2/a2",
        "",  # r-0002: unknown unit re-asked, then an edit of the proposal
        "n",
        "",  # r-0003 delegation marked not a reference
        "c",
        "ok",  # r-0004 range
        "c",
        "",  # r-0005 (rest batch)
        "m",
        "external",
        "",  # r-0006 targeted negative: missed generic reference
        "n",
        "",  # r-0007 random negative
    ]
    code, out, _ = _run(["refs-label", "--file", str(path)], answers, law)
    assert code == 0
    assert "[[Undang-Undang ini]]" in out
    assert "proposed: s/p2/a1" in out
    assert "not a unit of the source" in out
    items = {i.item_id: i for i in load_ref_items(path)}
    assert items["r-0001"].verdict == "correct"
    assert items["r-0001"].gold_targets == ["SELF"]
    assert items["r-0002"].gold_targets == ["s/p2/a1", "s/p2/a2"]
    assert (items["r-0003"].verdict, items["r-0003"].gold_targets) == ("not_reference", [])
    assert items["r-0004"].notes == "ok"
    assert (items["r-0006"].verdict, items["r-0006"].gold_targets) == ("missed", ["EXTERNAL"])
    assert "[[ketentuan]] [[peraturan]]" in out
    assert all(i.annotator == "faqih" for i in items.values())

    report = tmp_path / "report.md"
    code, out, _ = _run(["refs-report", "--file", str(path), "--out", str(report)], [], law)
    assert code == 0
    text = report.read_text(encoding="utf-8")
    assert "Labeled: 7 of 7" in text
    assert (
        "| overall | 7 | 57.1% [25.0-84.2] | 5 | 1 | 2 | 83.3% [43.6-97.0] | 71.4% [35.9-91.8] |"
        in text
    )
    assert "| mentions | 5 |" in text
    assert "| negatives:targeted | 1 | 0.0% [0.0-79.3] | 0 | 0 | 1 | - | 0.0% [0.0-79.3] |" in text
    assert "overlapping slices" in text
    assert "[TARGET]" in text


def test_quit_keeps_saved_labels(tmp_path: Path, law: LawText) -> None:
    path = tmp_path / "sample.jsonl"
    _run(["refs-sample", "--file", str(path), *SAMPLE], [], law)
    _run(["refs-label", "--file", str(path)], ["c", "", ":quit"], law)
    labeled = [i.item_id for i in load_ref_items(path) if i.verdict]
    assert labeled == ["r-0001"]
