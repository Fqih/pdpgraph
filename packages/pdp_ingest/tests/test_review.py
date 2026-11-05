# SPDX-License-Identifier: Apache-2.0
"""Owner review list: order, progress counts, and review lines kept across regeneration (M1.2)."""

from pathlib import Path

import pytest

from pdp_ingest.canonical import blocks
from pdp_ingest.crosscheck import crosscheck
from pdp_ingest.overrides import Override, apply_overrides
from pdp_ingest.pipeline import TextResult
from pdp_ingest.registry import SourceEntry, load_source
from pdp_ingest.review import PENDING_LINE, Review, ReviewError, read_reviews, review_markdown
from pdp_ingest.segment import segment

REPO = Path(__file__).resolve().parents[3]
HTML = (
    "<p>BAB I</p><p>UMUM</p><p>Pasal 1</p><p>Data hadan publik dilindungi aman.</p>"
    "<p>Pasal 2</p><p>Subjek berhak atas informasi tentang tujuan pemrosesam.</p>"
    "<p>Pasal 3</p><p>Pengendali wajib dan Prosesor menjaga data.</p>"
    "<p>PENJELASAN</p><p>I UMUM</p><p>Umum.</p><p>II PASAL DEMI PASAL</p>"
    "<p>Pasal 1</p><p>Cukup jelas.</p><p>Pasal 2</p><p>Cukup jelas.</p>"
    "<p>Pasal 3</p><p>Cukup jelas.</p>"
)
PAGES = [
    "Pasal 1\nData badan publik dilindungi aman.\nPasal 2\n"
    "Subjek berhak atas informasi tentang tujuan pemrosesan.\n"
    "Pasal 3\nPengendali wajib dari Prosesor menjaga data.",
    "PENJELASAN\nI UMUM\nUmum.\nPasal 1\nCukup jelas.\nPasal 2\nCukup jelas.\n"
    "Pasal 3\nCukup jelas.",
]
TYPO = Override(unit_id="s/p1", find="hadan", replace="badan", reason="typo", pdf_page=1)
MEANING = Override(
    unit_id="s/p3",
    find="wajib dan",
    replace="wajib dari",
    reason="dan for dari",
    pdf_page=1,
    confirmed_by="faqih",
    changes_meaning=True,
)


@pytest.fixture
def entry() -> SourceEntry:
    return load_source("uu27-2022", REPO / "configs" / "sources").model_copy(
        update={"source_id": "s"}
    )


@pytest.fixture
def result() -> TextResult:
    extracted = blocks(HTML)
    seg = segment("s", extracted, explanation_marker="PENJELASAN")
    units = apply_overrides(seg.units, [TYPO, MEANING])
    ref, findings = crosscheck(units, PAGES)
    return TextResult(extracted, seg, [TYPO, MEANING], units, findings, ref.split_page)


def _md(entry: SourceEntry, result: TextResult, reviews: dict | None = None) -> str:  # type: ignore[type-arg]
    return review_markdown(entry, result, reviews, snapshot=("p1",), priority={"p2": "check x"})


def test_sections_follow_the_owner_review_order(entry: SourceEntry, result: TextResult) -> None:
    md = _md(entry, result)
    heads = [line for line in md.splitlines() if line.startswith("## ")]
    assert heads == [
        "## 1. Meaning-changing overrides and priority units",
        "## 2. Other overrides",
        "## 3. Snapshot units",
        "## 4. Flagged units",
    ]
    first, second = md.split("## 2.")[0], md.split("## 2.")[1].split("## 3.")[0]
    assert "| `s/p3` | wajib dan | wajib dari | 1 | dan for dari | faqih |" in first
    assert "`s/p2` Pasal 2: check x; flagged, review in §4" in first
    assert "| `s/p1` | hadan | badan | 1 | typo | - |" in second
    assert "### `s/p2` Pasal 2: coverage" in md.split("## 4.")[1]
    assert "### `s/p1`" not in md.split("## 4.")[1]  # fixed by its override


def test_every_snapshot_and_flagged_unit_has_a_pending_review_line(
    entry: SourceEntry, result: TextResult
) -> None:
    md = _md(entry, result)
    assert md.count(PENDING_LINE) == 2  # snapshot s/p1, flagged s/p2
    assert "Overrides: 2 total, 1 unconfirmed." in md
    assert "Snapshot units reviewed: 0 of 1. Flagged units reviewed: 0 of 1." in md


def test_review_lines_survive_regeneration(entry: SourceEntry, result: TextResult) -> None:
    md = _md(entry, result)
    done = "Review: reviewed_by: faqih | verdict: ocr_noise"
    head, flagged = md.split("## 4.")
    edited = head + "## 4." + flagged.replace(PENDING_LINE, done)
    reviews = read_reviews(edited)
    assert reviews == {("4", "s/p2"): Review("faqih", "ocr_noise")}
    regenerated = _md(entry, result, reviews)
    assert regenerated == edited.replace(
        "Flagged units reviewed: 0 of 1.", "Flagged units reviewed: 1 of 1 (ocr_noise 1)."
    )
    assert read_reviews(regenerated) == reviews


@pytest.mark.parametrize(
    "line",
    [
        "Review: reviewed_by: faqih | verdict: fine",
        "Review: reviewed_by: faqih | verdict: -",
        "Review: reviewed_by: - | verdict: komdigi_ok",
    ],
)
def test_invalid_review_lines_fail(line: str) -> None:
    with pytest.raises(ReviewError):
        read_reviews(f"## 4. Flagged units\n\n### `s/p2` Pasal 2\n\n{line}\n")
