# SPDX-License-Identifier: Apache-2.0
"""Definitions, term usage and data categories on a synthetic law (M1.4, FR-PDP-04)."""

import pytest

from pdp_ingest.canonical import blocks
from pdp_ingest.defs import (
    DefsError,
    data_categories,
    extract_definitions,
    link_terms,
    term_list,
)
from pdp_ingest.refs import extract_refs
from pdp_ingest.segment import Unit, segment

HTML = (
    "<p>BAB I</p><p>UMUM</p>"
    "<p>Pasal 1</p><p>Dalam Undang-Undang ini yang dimaksud dengan:</p><ol>"
    "<li><p>Data Pribadi adalah data tentang orang.</p></li>"
    "<li><p>Subjek Data Pribadi adalah orang yang melekat Data Pribadi.</p></li>"
    "<li><p>Data Pribadi yang Spesifik adalah Data Pribadi yang sensitif.</p></li>"
    "<li><p>Pemerintah Pusat yang selanjutnya disebut Pemerintah adalah Presiden.</p></li>"
    "</ol>"
    "<p>Pasal 2</p><p>Data Pribadi yang Spesifik dan Data Pribadi milik subjek Data Pribadi "
    "dilindungi; pemrosesan data pribadi oleh Pemerintah diatur dengan Peraturan Pemerintah.</p>"
    "<p>Pasal 3</p><ol>"
    "<li><p>Data Pribadi terdiri atas:</p><ol>"
    "<li><p>Data Pribadi yang bersifat spesifik; dan</p></li>"
    "<li><p>Data Pribadi yang bersifat umum.</p></li></ol></li>"
    "<li><p>Data Pribadi yang bersifat spesifik sebagaimana dimaksud pada ayat (1) huruf a "
    "meliputi:</p><ol>"
    "<li><p>data dan informasi kesehatan;</p></li>"
    "<li><p>data anak; dan/atau</p></li>"
    "<li><p>data lainnya sesuai dengan ketentuan peraturan perundang-undangan.</p></li></ol></li>"
    "<li><p>Data Pribadi yang bersifat umum sebagaimana dimaksud pada ayat (1) huruf b "
    "meliputi:</p><ol>"
    "<li><p>nama lengkap; dan/atau</p></li>"
    "<li><p>Data Pribadi yang dikombinasikan untuk mengidentifikasi seseorang.</p></li>"
    "</ol></li></ol>"
    "<p>PENJELASAN</p><p>I UMUM</p><p>Pemerintah melindungi Data Pribadinya warga.</p>"
    "<p>II PASAL DEMI PASAL</p><p>Pasal 1</p><p>Cukup jelas.</p>"
    "<p>Pasal 2</p><p>Cukup jelas.</p>"
    "<p>Pasal 3</p><p>Ayat (2)</p><p>Huruf a</p>"
    '<p>Yang dimaksud dengan "data dan informasi kesehatan" adalah catatan kesehatan.</p>'
    "<p>Huruf b</p><p>Cukup jelas.</p>"
)
S = "s"


@pytest.fixture(scope="module")
def units() -> list[Unit]:
    return segment(S, blocks(HTML), explanation_marker="PENJELASAN").units


def test_definitions_with_alias_and_slugs(units: list[Unit]) -> None:
    defs = extract_definitions(units)
    got = [(d.node_id, d.unit_id, d.term, d.aliases) for d in defs]
    assert got == [
        ("s/def/data-pribadi", "s/p1/n1", "Data Pribadi", ()),
        ("s/def/subjek-data-pribadi", "s/p1/n2", "Subjek Data Pribadi", ()),
        ("s/def/data-pribadi-yang-spesifik", "s/p1/n3", "Data Pribadi yang Spesifik", ()),
        ("s/def/pemerintah-pusat", "s/p1/n4", "Pemerintah Pusat", ("Pemerintah",)),
    ]
    assert defs[0].text == "Data Pribadi adalah data tentang orang."
    assert defs[0].term_norm == "data pribadi"


def test_definition_unit_without_adalah_is_an_error(units: list[Unit]) -> None:
    broken = [
        Unit(u.unit_id, u.kind, u.label, "Data Pribadi ialah data.", u.parent_id, u.order)
        if u.unit_id == "s/p1/n1"
        else u
        for u in units
    ]
    with pytest.raises(DefsError, match="s/p1/n1"):
        extract_definitions(broken)


def _uses(units: list[Unit], unit: str) -> dict[tuple[str, str], tuple[int, list[str]]]:
    defs = extract_definitions(units)
    text = {u.unit_id: u.text for u in units}[f"{S}/{unit}"]
    return {
        (u.node_id.removeprefix("s/def/"), u.kind): (u.count, [text[a:b] for a, b in u.spans])
        for u in link_terms(units, defs, extract_refs(units))
        if u.unit_id == f"{S}/{unit}"
    }


def test_longest_match_first_and_informal_matches(units: list[Unit]) -> None:
    assert _uses(units, "p2") == {
        ("data-pribadi-yang-spesifik", "defined"): (1, ["Data Pribadi yang Spesifik"]),
        ("data-pribadi", "defined"): (2, ["Data Pribadi", "Data Pribadi"]),
        ("subjek-data-pribadi", "informal"): (1, ["subjek Data Pribadi"]),
        ("data-pribadi", "informal"): (1, ["data pribadi"]),
        ("pemerintah-pusat", "defined"): (1, ["Pemerintah"]),
    }


def test_instrument_names_are_not_term_usage(units: list[Unit]) -> None:
    spans = _uses(units, "p2")[("pemerintah-pusat", "defined")][1]
    assert spans == ["Pemerintah"]  # "Peraturan Pemerintah" is a delegation mention


def test_definition_does_not_link_its_own_term(units: list[Unit]) -> None:
    assert _uses(units, "p1/n2") == {("data-pribadi", "defined"): (1, ["Data Pribadi"])}
    assert _uses(units, "p1/n1") == {}
    assert ("data-pribadi", "defined") in _uses(units, "p1/n3")
    assert _uses(units, "p1/n4") == {}


def test_enclitic_and_penjelasan_units(units: list[Unit]) -> None:
    assert _uses(units, "pj-umum") == {
        ("pemerintah-pusat", "defined"): (1, ["Pemerintah"]),
        ("data-pribadi", "defined"): (1, ["Data Pribadinya"]),
    }


def test_confidence_follows_kind(units: list[Unit]) -> None:
    defs = extract_definitions(units)
    uses = link_terms(units, defs, extract_refs(units))
    assert {(u.kind, u.confidence) for u in uses} == {("defined", "high"), ("informal", "low")}


def test_term_list(units: list[Unit]) -> None:
    assert term_list(extract_definitions(units)) == [
        "Data Pribadi",
        "Data Pribadi yang Spesifik",
        "Pemerintah",
        "Pemerintah Pusat",
        "Subjek Data Pribadi",
    ]


def test_data_categories_from_classification_article(units: list[Unit]) -> None:
    cats = data_categories(units, pasal="p3")
    got = [(c.code, c.unit_id, c.parent_code, c.open) for c in cats]
    assert got == [
        ("SPESIFIK", "s/p3/a1/ha", None, False),
        ("UMUM", "s/p3/a1/hb", None, False),
        ("KESEHATAN", "s/p3/a2/ha", "SPESIFIK", False),
        ("ANAK", "s/p3/a2/hb", "SPESIFIK", False),
        ("LAINNYA", "s/p3/a2/hc", "SPESIFIK", True),
        ("NAMA_LENGKAP", "s/p3/a3/ha", "UMUM", False),
        ("DIKOMBINASIKAN_UNTUK_MENGIDENTIFIKASI_SESEORANG", "s/p3/a3/hb", "UMUM", False),
    ]
    assert cats[2].label == "data dan informasi kesehatan"
    assert cats[2].explanation == (
        'Yang dimaksud dengan "data dan informasi kesehatan" adalah catatan kesehatan.'
    )
    assert cats[3].explanation is None  # "Cukup jelas." carries no content
    assert {c.status for c in cats} == {"proposed"}


def test_data_categories_need_the_classification_ayat(units: list[Unit]) -> None:
    with pytest.raises(DefsError, match="terdiri atas"):
        data_categories(units, pasal="p2")
