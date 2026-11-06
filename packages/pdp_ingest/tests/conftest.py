# SPDX-License-Identifier: Apache-2.0
"""Synthetic stage artifacts for the graph and index tests (M1.5, M1.6)."""

from collections.abc import Callable
from pathlib import Path

import pytest

from pdp_ingest.canonical import blocks
from pdp_ingest.defs import data_categories, extract_definitions, link_terms
from pdp_ingest.defs_review import defs_markdown
from pdp_ingest.pipeline import write_graph_artifacts
from pdp_ingest.refs import extract_refs
from pdp_ingest.review import Review
from pdp_ingest.segment import segment

Artifacts = Callable[..., Path]

HTML = (
    "<p>BAB I</p><p>UMUM</p><p>Bagian Kesatu</p><p>Definisi</p>"
    "<p>Pasal 1</p><p>Dalam Undang-Undang ini yang dimaksud dengan:</p><ol>"
    "<li><p>Data Pribadi adalah data tentang orang.</p></li>"
    "<li><p>Korporasi adalah kumpulan orang.</p></li></ol>"
    "<p>BAB II</p><p>JENIS</p>"
    "<p>Pasal 2</p><ol>"
    "<li><p>Data Pribadi terdiri atas:</p><ol>"
    "<li><p>Data Pribadi yang bersifat spesifik; dan</p></li>"
    "<li><p>Data Pribadi yang bersifat umum.</p></li></ol></li>"
    "<li><p>Data Pribadi yang bersifat spesifik meliputi:</p><ol>"
    "<li><p>data anak.</p></li></ol></li></ol>"
    "<p>Pasal 3</p><p>Korporasi memproses Data Pribadi sebagaimana dimaksud dalam Pasal 2 ayat (1) "
    "dan korporasi lain diatur dengan Peraturan Pemerintah menurut Undang-Undang ini.</p>"
    "<p>PENJELASAN</p><p>I UMUM</p><p>Umum.</p><p>II PASAL DEMI PASAL</p>"
    "<p>Pasal 1</p><p>Cukup jelas.</p><p>Pasal 2</p><p>Ayat (1)</p><p>Lihat Pasal 3.</p>"
    "<p>Ayat (2)</p><p>Cukup jelas.</p><p>Pasal 3</p><p>Cukup jelas.</p>"
)
S = "s"
SOURCE = {
    "source_id": S,
    "title": "Undang-Undang Sintetis",
    "instrument_type": "UU",
    "number": 1,
    "year": 2000,
    "enacted_on": "2000-01-02",
    "promulgated_on": "2000-01-02",
    "effective_from": "2000-01-03",
    "url": "https://example.invalid/s",
    "body_sha256": "a" * 64,
    "canonicalization_version": 1,
    "parser_version": "pdp_ingest@0.0.0",
    "segment_version": 1,
    "refs_version": 1,
    "defs_version": 1,
    "overrides_total": 2,
    "overrides_unconfirmed": 1,
}


def _make(tmp_path: Path, reviews: dict[tuple[str, str], Review] | None = None) -> Path:
    seg = segment(S, blocks(HTML), explanation_marker="PENJELASAN")
    units = seg.units
    mentions = extract_refs(units)
    defs = extract_definitions(units)
    uses = link_terms(units, defs, mentions)
    cats = data_categories(units, pasal="p2")
    out = tmp_path / "processed" / S
    write_graph_artifacts(out, SOURCE, seg.structures, units, mentions, defs, uses, cats)
    review = tmp_path / "review" / S / "definitions.md"
    review.parent.mkdir(parents=True)
    review.write_text(defs_markdown(S, defs, uses, cats, units, reviews), encoding="utf-8")
    return tmp_path


@pytest.fixture
def artifacts(tmp_path: Path) -> Artifacts:
    """`artifacts(reviews=None)` writes the synthetic source "s"; returns the root holding
    `processed/s` and `review/s`."""

    def make(reviews: dict[tuple[str, str], Review] | None = None) -> Path:
        return _make(tmp_path, reviews)

    return make
