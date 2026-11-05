# SPDX-License-Identifier: Apache-2.0
"""Cross-check of units against a synthetic PDF text layer (M1.2)."""

import pytest

from pdp_ingest.crosscheck import THRESHOLD, Reference, crosscheck
from pdp_ingest.segment import Unit

PAGES = [
    "SALINAN\nPasal 1\nPengendali Data Pribadi wajib menjaga kerahasiaan Data Pribadi.\n"
    "SK No 123456A\nPasal 2 . . .",
    "-2-\nPasal 2\nSubjek Data Pribadi berhak mendapatkan informasi tentang tujuan pemrosesan.",
    "PENJELASAN\nATAS\nPasal 1\nYang dimaksud dengan kerahasiaan adalah keadaan tertutup.",
]


def _u(uid: str, text: str, kind: str = "PASAL") -> Unit:
    return Unit(uid, kind, uid, text, None, 0)


def test_reference_splits_at_penjelasan_and_strips_page_noise() -> None:
    ref = Reference(PAGES)
    assert ref.split_page == 3
    f = ref.check(_u("s/p1", "Pengendali Data Pribadi wajib menjaga kerahasiaan Data Pribadi."))
    assert (f.coverage, f.unmatched, f.diffs, f.pdf_page) == (1.0, [], [], 1)
    assert not f.needs_review


def test_penjelasan_units_are_checked_against_penjelasan_pages_only() -> None:
    ref = Reference(PAGES)
    pj = ref.check(
        _u("s/p1#pj", "Yang dimaksud dengan kerahasiaan adalah keadaan tertutup.", "PENJELASAN")
    )
    assert (pj.coverage, pj.pdf_page) == (1.0, 3)
    body = ref.check(_u("s/p9", "Yang dimaksud dengan kerahasiaan adalah keadaan tertutup."))
    assert body.coverage == 0.0
    assert body.pdf_page is None


def test_html_typo_is_flagged_with_aligned_pdf_words() -> None:
    units = [
        _u("s/p1", "Pengendali Data Pribadi wajib menjaga kerahasiaan Data Pribadi."),
        _u("s/p2", "Subjek Data Pribadi berhak mendapatkan informasi tentang tujuan pemrosesam."),
    ]
    _, (ok, typo) = crosscheck(units, PAGES)
    assert not ok.needs_review
    assert typo.coverage < 1.0
    assert typo.unmatched == ["informasi tentang tujuan [pemrosesam]"]
    assert [(d.html, d.pdf) for d in typo.diffs] == [("pemrosesam", "pemrosesan")]
    assert typo.needs_review


def test_pdf_side_ocr_error_is_attributed_to_pdf() -> None:
    pages = [PAGES[0].replace("kerahasiaan", "kerahasiaarr"), *PAGES[1:]]
    units = [
        _u("s/p1", "Pengendali Data Pribadi wajib menjaga kerahasiaan Data Pribadi."),
        _u("s/p3", "Menjaga kerahasiaan dan keamanan."),
    ]
    _, (f, _) = crosscheck(units, pages)
    assert [d.suspect for d in f.diffs] == ["pdf"]
    assert f.coverage < THRESHOLD
    assert f.needs_review  # low coverage still goes to the owner


def test_empty_unit_and_missing_penjelasan() -> None:
    ref = Reference(PAGES)
    assert ref.check(_u("s/p4", "")).coverage == 1.0
    with pytest.raises(ValueError, match="no Penjelasan"):
        Reference(PAGES[:2])
