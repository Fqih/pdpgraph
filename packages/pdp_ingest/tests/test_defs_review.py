# SPDX-License-Identifier: Apache-2.0
"""Committed definitions review list (M1.4): content, and review lines kept on regeneration."""

import pytest

from pdp_ingest.canonical import blocks
from pdp_ingest.defs import data_categories, extract_definitions, link_terms
from pdp_ingest.defs_review import (
    CATEGORY_SECTION,
    DEFINITION_SECTION,
    defs_markdown,
    read_defs_reviews,
)
from pdp_ingest.refs import extract_refs
from pdp_ingest.review import PENDING_LINE, Review, ReviewError
from pdp_ingest.segment import segment

HTML = (
    "<p>BAB I</p><p>UMUM</p>"
    "<p>Pasal 1</p><p>Dalam Undang-Undang ini yang dimaksud dengan:</p><ol>"
    "<li><p>Data Pribadi adalah data tentang orang.</p></li>"
    "<li><p>Pemerintah Pusat yang selanjutnya disebut Pemerintah adalah Presiden.</p></li></ol>"
    "<p>Pasal 2</p><ol>"
    "<li><p>Data Pribadi terdiri atas:</p><ol>"
    "<li><p>Data Pribadi yang bersifat spesifik; dan</p></li>"
    "<li><p>Data Pribadi yang bersifat umum.</p></li></ol></li>"
    "<li><p>Data Pribadi yang bersifat spesifik meliputi:</p><ol>"
    "<li><p>data anak.</p></li></ol></li></ol>"
    "<p>Pasal 3</p><p>Pemerintah memproses data pribadi.</p>"
    "<p>PENJELASAN</p><p>I UMUM</p><p>Umum.</p><p>II PASAL DEMI PASAL</p>"
    "<p>Pasal 1</p><p>Cukup jelas.</p><p>Pasal 2</p><p>Cukup jelas.</p>"
    "<p>Pasal 3</p><p>Cukup jelas.</p>"
)


def _render(reviews: dict[tuple[str, str], Review] | None = None) -> str:
    units = segment("s", blocks(HTML), explanation_marker="PENJELASAN").units
    defs = extract_definitions(units)
    uses = link_terms(units, defs, extract_refs(units))
    return defs_markdown("s", defs, uses, data_categories(units, pasal="p2"), units, reviews)


def test_lists_definitions_categories_terms_and_informal_uses() -> None:
    text = _render()
    assert "### `s/p1/n2` Pemerintah Pusat" in text
    assert "Node: `s/def/pemerintah-pusat`; aliases: Pemerintah; PDF page -" in text
    assert "> Data Pribadi adalah data tentang orang." in text
    assert "Defined uses: 1 in 1 unit(s); informal: 0" in text  # Pemerintah in Pasal 3
    assert "### `s/p2/a1/ha` SPESIFIK" in text
    assert "### `s/p2/a2/ha` ANAK (member of SPESIFIK)" in text
    assert "Status: proposed" in text
    assert "Data Pribadi, Pemerintah, Pemerintah Pusat" in text
    assert "| `s/p3` | Data Pribadi | data pribadi |" in text
    assert text.count(PENDING_LINE) == 2 + 3


def test_reviews_survive_regeneration_and_confirm_codes() -> None:
    reviews = {
        (DEFINITION_SECTION, "s/p1/n1"): Review("faqih", "ok"),
        (CATEGORY_SECTION, "s/p2/a2/ha"): Review("faqih", "confirmed"),
    }
    text = _render(reviews)
    assert read_defs_reviews(text) == reviews
    assert "Status: confirmed" in text
    assert "Definitions reviewed: 1 of 2 (ok 1)" in text
    assert "Categories reviewed: 1 of 3 (confirmed 1)" in text
    assert _render(read_defs_reviews(text)) == text


def test_verdict_must_fit_the_section() -> None:
    text = _render().replace(PENDING_LINE, "Review: reviewed_by: faqih | verdict: confirmed", 1)
    with pytest.raises(ReviewError, match="s/p1/n1"):
        read_defs_reviews(text)
