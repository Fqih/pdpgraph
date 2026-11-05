# SPDX-License-Identifier: Apache-2.0
"""Term-link sample CLI: build, label, report (M1.4). Labels here are synthetic test data."""

import io
from collections.abc import Iterator
from pathlib import Path

import pytest

from pdp_eval.cli import main
from pdp_eval.law import LawText
from pdp_eval.termsample import load_term_items
from pdp_ingest.segment import Unit


@pytest.fixture
def law(term_units: list[Unit]) -> LawText:
    return LawText("s", term_units)


def _run(argv: list[str], answers: list[str], law: LawText) -> tuple[int, str]:
    feed: Iterator[str] = iter(answers)
    out = io.StringIO()
    return main(argv, ask=lambda _: next(feed), out=out, law=law), out.getvalue()


SAMPLE = ["--defined", "3", "--informal", "2", "--seed", "3"]


def test_sample_label_report(tmp_path: Path, law: LawText) -> None:
    path = tmp_path / "pdp-terms" / "v0" / "sample.jsonl"
    code, out = _run(["terms-sample", "--file", str(path), *SAMPLE], [], law)
    assert code == 0
    assert "wrote 5 items" in out
    assert _run(["terms-sample", "--file", str(path), *SAMPLE], [], law)[0] == 1

    code, out = _run(
        ["terms-label", "--file", str(path)], ["c", "", "w", "odd", "c", "", ":quit"], law
    )
    assert code == 0
    assert "[[" in out
    assert "labeled 3 of 5" in out
    items = load_term_items(path)
    assert [i.verdict for i in items[:3]] == ["correct", "wrong", "correct"]
    assert items[1].notes == "odd"
    assert {i.annotator for i in items[:3]} == {"faqih"}

    report = tmp_path / "report.md"
    code, out = _run(["terms-report", "--file", str(path), "--out", str(report)], [], law)
    assert code == 0
    text = report.read_text(encoding="utf-8")
    assert "| defined | 3 | 2 | 66.7% [20.8-93.9] |" in text
    assert "Labeled: 3 of 5" in text
