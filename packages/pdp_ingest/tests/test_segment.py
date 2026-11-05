# SPDX-License-Identifier: Apache-2.0
"""`segment` grammar on synthetic bodies in the Komdigi page shape (M1.2, FR-PDP-01)."""

import pytest

from common import ids
from pdp_ingest.canonical import blocks
from pdp_ingest.segment import SegmentError, segment

HTML = (
    "<p>UNDANG-UNDANG</p><p>menimbang</p><ol><li><p>bahwa ...;</p></li></ol>"
    "<p>BAB I</p><p>KETENTUAN UMUM</p>"
    "<p>Pasal 1</p><p>Dalam Undang-Undang ini yang dimaksud dengan:</p>"
    "<ol><li><p>Data adalah data.</p></li><li><p>Subjek adalah orang.</p></li></ol>"
    "<p>BAB II</p><p>RUANG LINGKUP</p><p>Bagian Kesatu</p><p>Umum</p>"
    "<p>Pasal 2</p><ol><li><p>Berlaku untuk:</p><ol><li><p>di dalam;</p></li>"
    "<li><p>di luar, yang berakibat:</p><ol><li><p>di wilayah;</p></li></ol></li></ol></li>"
    "<li><p>Tidak berlaku untuk rumah tangga.</p><p>Lanjutan ayat.</p></li></ol>"
    "<p>Paragraf 1</p><p>Asas</p>"
    "<p>Pasal 2A</p><p>Asas:</p><ol><li><p>pelindungan;</p></li><li><p>kepastian.</p></li></ol>"
    "<p>Pasal 3</p><p>Undang-Undang ini mulai berlaku pada tanggal diundangkan.</p>"
    "<p>Agar setiap orang mengetahuinya, memerintahkan pengundangan.</p><p>ttd.</p>"
    "<p>PENJELASAN</p><p>TENTANG</p><p>I UMUM</p><p>Latar belakang.</p><p>Paragraf dua.</p>"
    "<p>II PASAL DEMI PASAL</p><p>Pasal 1</p><p>Cukup jelas.</p>"
    "<p>Pasal 2</p><p>Ayat 1</p><p>Huruf b</p><p>Akibat hukum.</p><p>Ayat (2)</p>"
    "<p>Cukup jelas</p><p>Pasal 2A</p><p>Huruf a</p><p>Cukup jelas.</p>"
    "<p>Pasal 3</p><p>Cukup jelas.</p>"
)


@pytest.fixture
def seg():  # type: ignore[no-untyped-def]
    return segment("uu27-2022", blocks(HTML), explanation_marker="PENJELASAN")


def test_structures_and_headings(seg) -> None:  # type: ignore[no-untyped-def]
    got = [(s.unit_id, s.kind, s.heading, s.parent_id) for s in seg.structures]
    assert got == [
        ("uu27-2022/bab1", "BAB", "KETENTUAN UMUM", None),
        ("uu27-2022/bab2", "BAB", "RUANG LINGKUP", None),
        ("uu27-2022/bab2/bag1", "BAGIAN", "Umum", "uu27-2022/bab2"),
        ("uu27-2022/bab2/bag1/par1", "PARAGRAF", "Asas", "uu27-2022/bab2/bag1"),
    ]


def test_body_units_ids_kinds_parents(seg) -> None:  # type: ignore[no-untyped-def]
    body = [(u.unit_id, u.kind, u.parent_id) for u in seg.units if u.kind != "PENJELASAN"]
    assert body == [
        ("uu27-2022/p1", "PASAL", "uu27-2022/bab1"),
        ("uu27-2022/p1/n1", "ANGKA", "uu27-2022/p1"),
        ("uu27-2022/p1/n2", "ANGKA", "uu27-2022/p1"),
        ("uu27-2022/p2", "PASAL", "uu27-2022/bab2/bag1"),
        ("uu27-2022/p2/a1", "AYAT", "uu27-2022/p2"),
        ("uu27-2022/p2/a1/ha", "HURUF", "uu27-2022/p2/a1"),
        ("uu27-2022/p2/a1/hb", "HURUF", "uu27-2022/p2/a1"),
        ("uu27-2022/p2/a1/hb/n1", "ANGKA", "uu27-2022/p2/a1/hb"),
        ("uu27-2022/p2/a2", "AYAT", "uu27-2022/p2"),
        ("uu27-2022/p2a", "PASAL", "uu27-2022/bab2/bag1/par1"),
        ("uu27-2022/p2a/ha", "HURUF", "uu27-2022/p2a"),
        ("uu27-2022/p2a/hb", "HURUF", "uu27-2022/p2a"),
        ("uu27-2022/p3", "PASAL", "uu27-2022/bab2/bag1/par1"),
    ]
    for unit in seg.units:
        assert ids.format(ids.parse(unit.unit_id)) == unit.unit_id


def test_unit_text_is_own_text_with_continuations(seg) -> None:  # type: ignore[no-untyped-def]
    units = seg.by_id()
    assert units["uu27-2022/p1"].text == "Dalam Undang-Undang ini yang dimaksud dengan:"
    assert units["uu27-2022/p2"].text == ""
    assert units["uu27-2022/p2/a1"].text == "Berlaku untuk:"
    assert units["uu27-2022/p2/a2"].text == "Tidak berlaku untuk rumah tangga.\nLanjutan ayat."
    assert units["uu27-2022/p3"].text == "Undang-Undang ini mulai berlaku pada tanggal diundangkan."
    assert units["uu27-2022/p2/a1/hb/n1"].label == "Pasal 2 ayat (1) huruf b angka 1"
    assert units["uu27-2022/p2a/hb"].label == "Pasal 2A huruf b"


def test_preamble_and_closing_are_not_units(seg) -> None:  # type: ignore[no-untyped-def]
    texts = " ".join(u.text for u in seg.units)
    assert "bahwa" not in texts
    assert "Agar setiap orang" not in texts
    assert "ttd." not in texts


def test_penjelasan_mapping(seg) -> None:  # type: ignore[no-untyped-def]
    pj = {u.unit_id: (u.text, u.parent_id, u.label) for u in seg.units if u.kind == "PENJELASAN"}
    assert pj == {
        "uu27-2022/pj-umum": ("Latar belakang.\nParagraf dua.", None, "Penjelasan Umum"),
        "uu27-2022/p1#pj": ("Cukup jelas.", "uu27-2022/p1", "Penjelasan Pasal 1"),
        "uu27-2022/p2/a1/hb#pj": (
            "Akibat hukum.",
            "uu27-2022/p2/a1/hb",
            "Penjelasan Pasal 2 ayat (1) huruf b",
        ),
        "uu27-2022/p2/a2#pj": ("Cukup jelas", "uu27-2022/p2/a2", "Penjelasan Pasal 2 ayat (2)"),
        "uu27-2022/p2a/ha#pj": ("Cukup jelas.", "uu27-2022/p2a/ha", "Penjelasan Pasal 2A huruf a"),
        "uu27-2022/p3#pj": ("Cukup jelas.", "uu27-2022/p3", "Penjelasan Pasal 3"),
    }


def test_orders_are_increasing(seg) -> None:  # type: ignore[no-untyped-def]
    orders = [u.order for u in seg.units]
    assert orders == sorted(orders)
    assert len(set(orders)) == len(orders)


@pytest.mark.parametrize(
    ("html", "message"),
    [
        (HTML.replace("<p>PENJELASAN</p>", "<p>X</p>"), "explanation marker"),
        (
            HTML.replace("<p>Pasal 2A</p><p>Huruf a</p>", "<p>Pasal 2A</p><p>Huruf z</p>"),
            "missing unit",
        ),
        (
            HTML.replace("<p>Pasal 3</p><p>Cukup jelas.</p>", "<p>Pasal 9</p><p>x</p>"),
            "missing unit",
        ),
        (HTML.replace("<p>Pasal 2A</p>", "<p>Pasal 2</p>"), "duplicate unit"),
        (HTML.replace("<p>Pasal 1</p><p>Dalam", "<p>Dalam"), "outside a Pasal"),
        (HTML.replace("<p>Ayat (2)</p>", "<p>Ayat 1</p>"), "duplicate Penjelasan"),
        (
            HTML.replace("<p>I UMUM</p><p>Latar belakang.</p><p>Paragraf dua.</p>", "")
            .replace(
                "<p>II PASAL DEMI PASAL</p>", "<p>I UMUM</p><p>x</p><p>II PASAL DEMI PASAL</p>"
            )
            .replace("<p>Pasal 1</p><p>Cukup jelas.</p>", "<p>Cukup jelas.</p>"),
            "without a header",
        ),
        (
            HTML.replace(
                "<li><p>di wilayah;</p></li>",
                "<li><p>di wilayah;</p><ol><li><p>x</p></li></ol></li>",
            ),
            "deeper than 3",
        ),
    ],
)
def test_structure_errors(html: str, message: str) -> None:
    with pytest.raises(SegmentError, match=message):
        segment("uu27-2022", blocks(html), explanation_marker="PENJELASAN")
