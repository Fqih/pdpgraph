# SPDX-License-Identifier: Apache-2.0
"""Reference grammar and resolver on a synthetic law (M1.3, FR-PDP-03)."""

import pytest

from pdp_ingest.canonical import blocks
from pdp_ingest.refs import Mention, extract_refs
from pdp_ingest.segment import segment

HTML = (
    "<p>BAB I</p><p>UMUM</p>"
    "<p>Pasal 1</p><p>Dalam Undang-Undang ini yang dimaksud dengan:</p>"
    "<ol><li><p>Data adalah data.</p></li><li><p>Subjek adalah orang.</p></li></ol>"
    "<p>Pasal 2</p><ol>"
    "<li><p>Berlaku bagi Subjek sebagaimana dimaksud dalam Pasal 1 angka 2, yaitu:</p><ol>"
    "<li><p>satu;</p></li><li><p>dua;</p></li><li><p>tiga.</p></li></ol></li>"
    "<li><p>Ketentuan sebagaimana dimaksud pada ayat (1) huruf a sampai dengan huruf c "
    "dikecualikan.</p></li>"
    "<li><p>Ketentuan lebih lanjut mengenai Data sebagaimana dimaksud pada ayat (1) dan ayat (2) "
    "diatur dalam Peraturan Pemerintah.</p></li></ol>"
    "<p>BAB II</p><p>HAK</p>"
    "<p>Pasal 3</p><p>Hak sebagaimana dimaksud dalam Pasal 1, Pasal 2 ayat (1) huruf b, dan "
    "Pasal 4 berlaku sesuai dengan Undang-Undang Nomor 11 Tahun 2008.</p>"
    "<p>Pasal 4</p><p>Pelanggaran terhadap Pasal 2 sampai dengan Pasal 5 dikenai pidana "
    "sebagaimana dimaksud dalam Kitab Undang-Undang Hukum Pidana.</p>"
    "<p>Pasal 5</p><p>Ketentuan Pasal 9 ayat (1) tidak berlaku, sesuai amanat Pasal 28G ayat (1) "
    "Undang-Undang Dasar Negara Republik Indonesia Tahun 1945.</p>"
    "<p>Pasal 5A</p><p>Mengacu pada Pasal 5A dan Pasal 3 Undang-Undang ini, lembaga diatur dengan "
    "Peraturan Presiden.</p>"
    "<p>PENJELASAN</p><p>I UMUM</p><p>Umum, lihat Pasal 3. Juga ayat (1).</p>"
    "<p>II PASAL DEMI PASAL</p><p>Pasal 1</p><p>Cukup jelas.</p>"
    "<p>Pasal 2</p><p>Ayat (1)</p><p>Termasuk huruf b dan ayat (3).</p>"
    "<p>Ayat (2)</p><p>Cukup jelas.</p><p>Ayat (3)</p><p>Cukup jelas.</p>"
    "<p>Pasal 3</p><p>Cukup jelas.</p><p>Pasal 4</p><p>Cukup jelas.</p>"
    "<p>Pasal 5</p><p>Cukup jelas.</p><p>Pasal 5A</p><p>Cukup jelas.</p>"
)
S = "s"


@pytest.fixture(scope="module")
def mentions() -> list[Mention]:
    seg = segment(S, blocks(HTML), explanation_marker="PENJELASAN")
    return extract_refs(seg.units)


def _in(mentions: list[Mention], unit: str) -> list[Mention]:
    return [m for m in mentions if m.unit_id == f"{S}/{unit}"]


def _t(*ids: str) -> tuple[str, ...]:
    return tuple(f"{S}/{i}" for i in ids)


def test_spans_are_exact(mentions: list[Mention]) -> None:
    from pdp_ingest.segment import segment as seg_

    units = {
        u.unit_id: u.text for u in seg_(S, blocks(HTML), explanation_marker="PENJELASAN").units
    }
    assert mentions
    for m in mentions:
        assert units[m.unit_id][m.start : m.end] == m.text


def test_self_reference_has_no_target(mentions: list[Mention]) -> None:
    (m,) = _in(mentions, "p1")
    assert (m.text, m.kind, m.resolution, m.targets) == (
        "Undang-Undang ini",
        "REFERENCE",
        "SELF",
        (),
    )
    assert m.patterns == ("self",)


def test_absolute_with_angka_and_sebagaimana(mentions: list[Mention]) -> None:
    (m,) = _in(mentions, "p2/a1")
    assert m.text == "sebagaimana dimaksud dalam Pasal 1 angka 2"
    assert (m.resolution, m.targets) == ("EXACT", _t("p1/n2"))
    assert m.patterns == ("sebagaimana", "absolute")


def test_relative_huruf_range_expands_one_target_per_unit(mentions: list[Mention]) -> None:
    (m,) = _in(mentions, "p2/a2")
    assert m.text == "sebagaimana dimaksud pada ayat (1) huruf a sampai dengan huruf c"
    assert m.targets == _t("p2/a1/ha", "p2/a1/hb", "p2/a1/hc")
    assert m.patterns == ("sebagaimana", "relative", "range")


def test_delegation_is_its_own_mention_kind(mentions: list[Mention]) -> None:
    ref, dlg = _in(mentions, "p2/a3")
    assert ref.targets == _t("p2/a1", "p2/a2")
    assert ref.patterns == ("sebagaimana", "relative", "list")
    assert (dlg.text, dlg.kind, dlg.resolution) == (
        "diatur dalam Peraturan Pemerintah",
        "DELEGATION",
        "EXTERNAL_UNRESOLVED",
    )
    assert (dlg.instrument, dlg.targets, dlg.patterns) == (
        "Peraturan Pemerintah",
        (),
        ("delegation",),
    )


def test_list_with_inheritance_and_external_instrument(mentions: list[Mention]) -> None:
    ref, ext = _in(mentions, "p3")
    assert ref.text == "sebagaimana dimaksud dalam Pasal 1, Pasal 2 ayat (1) huruf b, dan Pasal 4"
    assert ref.targets == _t("p1", "p2/a1/hb", "p4")
    assert ref.patterns == ("sebagaimana", "absolute", "list")
    assert (ext.text, ext.resolution, ext.instrument) == (
        "Undang-Undang Nomor 11 Tahun 2008",
        "EXTERNAL_UNRESOLVED",
        "Undang-Undang Nomor 11 Tahun 2008",
    )
    assert ext.patterns == ("external",)


def test_pasal_range_crosses_structures_and_includes_suffixed_pasal(
    mentions: list[Mention],
) -> None:
    ref, ext = _in(mentions, "p4")
    assert ref.text == "Pasal 2 sampai dengan Pasal 5"
    assert ref.targets == _t("p2", "p3", "p4", "p5")
    assert ext.text == "sebagaimana dimaksud dalam Kitab Undang-Undang Hukum Pidana"
    assert ext.instrument == "Kitab Undang-Undang Hukum Pidana"


def test_unresolved_internal_and_external_pasal(mentions: list[Mention]) -> None:
    missing, ext = _in(mentions, "p5")
    assert (missing.text, missing.resolution, missing.targets) == (
        "Pasal 9 ayat (1)",
        "UNRESOLVED",
        (),
    )
    assert missing.unresolved == ("Pasal 9 ayat (1)",)
    assert ext.text == (
        "Pasal 28G ayat (1) Undang-Undang Dasar Negara Republik Indonesia Tahun 1945"
    )
    assert (ext.resolution, ext.targets, ext.patterns) == (
        "EXTERNAL_UNRESOLVED",
        (),
        ("absolute", "external"),
    )


def test_suffix_pasal_self_qualifier_and_presidential_delegation(mentions: list[Mention]) -> None:
    ref, dlg = _in(mentions, "p5a")
    assert ref.text == "Pasal 5A dan Pasal 3 Undang-Undang ini"
    assert ref.targets == _t("p5a", "p3")
    assert dlg.instrument == "Peraturan Presiden"


def test_penjelasan_resolves_relative_to_explained_unit(mentions: list[Mention]) -> None:
    (m,) = _in(mentions, "p2/a1#pj")
    assert m.targets == _t("p2/a1/hb", "p2/a3")
    assert m.patterns == ("relative", "list", "penjelasan")


def test_relative_ref_without_context_is_unresolved(mentions: list[Mention]) -> None:
    absolute, relative = _in(mentions, "pj-umum")
    assert (absolute.targets, absolute.patterns) == (_t("p3"), ("absolute", "penjelasan"))
    assert (relative.resolution, relative.targets) == ("UNRESOLVED", ())
    assert relative.unresolved == ("ayat (1)",)


def test_mentions_are_ordered_by_unit_and_span(mentions: list[Mention]) -> None:
    keys = [(m.unit_id, m.start) for m in mentions]
    assert len(set(keys)) == len(keys)
    for unit in {m.unit_id for m in mentions}:
        starts = [m.start for m in mentions if m.unit_id == unit]
        assert starts == sorted(starts)


def test_diatur_dalam_undang_undang_ini_is_self_not_delegation() -> None:
    html = (
        "<p>BAB I</p><p>UMUM</p><p>Pasal 1</p><p>Dilaksanakan sesuai ketentuan yang diatur dalam "
        "Undang-Undang ini. Tata cara diatur dengan Undang-Undang.</p>"
        "<p>PENJELASAN</p><p>I UMUM</p><p>Umum.</p><p>II PASAL DEMI PASAL</p>"
        "<p>Pasal 1</p><p>Cukup jelas.</p>"
    )
    units = segment(S, blocks(html), explanation_marker="PENJELASAN").units
    got = [(m.text, m.kind, m.resolution) for m in extract_refs(units)]
    assert got == [
        ("Undang-Undang ini", "REFERENCE", "SELF"),
        ("diatur dengan Undang-Undang", "DELEGATION", "EXTERNAL_UNRESOLVED"),
    ]
