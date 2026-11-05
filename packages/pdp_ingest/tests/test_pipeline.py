# SPDX-License-Identifier: Apache-2.0
"""Review list rendering on a synthetic result (M1.2)."""

from pathlib import Path

from pdp_ingest.canonical import blocks
from pdp_ingest.crosscheck import crosscheck
from pdp_ingest.overrides import Override, apply_overrides
from pdp_ingest.pipeline import TextResult, review_markdown
from pdp_ingest.registry import load_source
from pdp_ingest.segment import segment

REPO = Path(__file__).resolve().parents[3]
HTML = (
    "<p>BAB I</p><p>UMUM</p><p>Pasal 1</p><p>Data hadan publik dilindungi aman.</p>"
    "<p>Pasal 2</p><p>Subjek berhak atas informasi tentang tujuan pemrosesam.</p>"
    "<p>PENJELASAN</p><p>I UMUM</p><p>Umum.</p><p>II PASAL DEMI PASAL</p>"
    "<p>Pasal 1</p><p>Cukup jelas.</p><p>Pasal 2</p><p>Cukup jelas.</p>"
)
PAGES = [
    "Pasal 1\nData badan publik dilindungi aman.\nPasal 2\n"
    "Subjek berhak atas informasi tentang tujuan pemrosesan.",
    "PENJELASAN\nI UMUM\nUmum.\nPasal 1\nCukup jelas.\nPasal 2\nCukup jelas.",
]


def test_review_lists_overrides_then_flagged_units() -> None:
    entry = load_source("uu27-2022", REPO / "configs" / "sources").model_copy(
        update={"source_id": "s"}
    )
    extracted = blocks(HTML)
    seg = segment("s", extracted, explanation_marker="PENJELASAN")
    fix = Override(unit_id="s/p1", find="hadan", replace="badan", reason="typo", pdf_page=1)
    units = apply_overrides(seg.units, [fix])
    ref, findings = crosscheck(units, PAGES)
    md = review_markdown(entry, TextResult(extracted, seg, [fix], units, findings, ref.split_page))

    assert md.index("## 1. Overrides") < md.index("## 2. Snapshot") < md.index("## 3. Flagged")
    assert "| `s/p1` | hadan | badan | 1 | typo | - |" in md
    assert "Overrides: 1 (1 unconfirmed). Flagged for review: 1" in md
    assert "### `s/p2` Pasal 2: coverage" in md
    assert "| pemrosesam | pemrosesan |" in md
    assert "### `s/p1`" not in md  # fixed by the override, so it matches the PDF
