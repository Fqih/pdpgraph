# SPDX-License-Identifier: Apache-2.0
"""Law text view for the labeling CLI: Pasal lines with suggested unit ids (M1.7)."""

import pytest

from pdp_eval.law import LawText


def _ids(law: LawText, n: int) -> list[tuple[str | None, str, str]]:
    return [(line.unit_id, line.label, line.text) for line in law.pasal(n)]


def test_definitions_are_angka(law: LawText) -> None:
    assert _ids(law, 1) == [
        ("uu27-2022/p1", "Pasal 1", ""),
        (None, "", "Dalam Undang-Undang ini yang dimaksud dengan:"),
        ("uu27-2022/p1/n1", "1.", "Data Pribadi adalah data."),
        ("uu27-2022/p1/n2", "2.", "Subjek adalah orang."),
    ]


def test_ayat_huruf_angka_nesting(law: LawText) -> None:
    assert [i for i, _, _ in _ids(law, 2)] == [
        "uu27-2022/p2",
        "uu27-2022/p2/a1",
        "uu27-2022/p2/a1/ha",
        "uu27-2022/p2/a1/hb",
        "uu27-2022/p2/a1/hb/n1",
        "uu27-2022/p2/a2",
    ]
    assert [lbl for _, lbl, _ in _ids(law, 2)][1:4] == ["(1)", "a.", "b."]


def test_intro_then_huruf_and_stops_before_closing_formula(law: LawText) -> None:
    assert _ids(law, 3) == [
        ("uu27-2022/p3", "Pasal 3", ""),
        (None, "", "Asas:"),
        ("uu27-2022/p3/ha", "a.", "pelindungan;"),
        ("uu27-2022/p3/hb", "b.", "kepastian."),
    ]


def test_pasal_stops_at_structure_heading(law: LawText) -> None:
    assert all("Bagian" not in text and text != "Umum" for _, _, text in _ids(law, 2))


def test_explanation_of_pasal_and_general(law: LawText) -> None:
    assert law.explanation(2) == ["Ayat (1)", "Huruf b", "Akibat hukum."]
    assert law.general_explanation() == ["I. UMUM", "Latar belakang.", "II. PASAL DEMI PASAL"]


@pytest.mark.parametrize(
    ("unit_id", "exists"),
    [
        ("uu27-2022/p2/a1/hb/n1", True),
        ("uu27-2022/p2/a1/hb/n1#pj", True),
        ("uu27-2022/pj-umum", True),
        ("uu27-2022/p2/a3", False),
        ("uu27-2022/p9", False),
        ("other-2020/p1", False),
    ],
)
def test_has_unit(law: LawText, unit_id: str, exists: bool) -> None:
    assert law.has_unit(unit_id) is exists


def test_unknown_pasal_is_an_error(law: LawText) -> None:
    with pytest.raises(KeyError, match="Pasal 9"):
        law.pasal(9)
