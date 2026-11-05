# SPDX-License-Identifier: Apache-2.0
"""ID grammar tests: every example in 04-data-model §2.2, rejections, round-trip (FR-PDP-02)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from common import ids
from common.errors import InvalidIdError
from common.ids import (
    DefinitionPath,
    NodeId,
    ObligationPath,
    PasalPath,
    PjUmum,
    Structure,
    UnitId,
)

SRC = "uu27-2022"

# Rows of 04 §2.2: (unit_id, node_id, expected unit).
EXAMPLES: list[tuple[str, str, UnitId]] = [
    ("uu27-2022/bab3", "uu27-2022/bab3@1", UnitId(SRC, Structure(bab=3))),
    (
        "uu27-2022/bab3/bag1/par2",
        "uu27-2022/bab3/bag1/par2@1",
        UnitId(SRC, Structure(bab=3, bagian=1, paragraf=2)),
    ),
    ("uu27-2022/p20", "uu27-2022/p20@1", UnitId(SRC, PasalPath(pasal=20))),
    ("uu27-2022/p20a", "uu27-2022/p20a@1", UnitId(SRC, PasalPath(pasal=20, pasal_suffix="a"))),
    ("uu27-2022/p20/a2", "uu27-2022/p20/a2@1", UnitId(SRC, PasalPath(pasal=20, ayat=2))),
    (
        "uu27-2022/p20/a1a",
        "uu27-2022/p20/a1a@1",
        UnitId(SRC, PasalPath(pasal=20, ayat=1, ayat_suffix="a")),
    ),
    (
        "uu27-2022/p20/a2/hb",
        "uu27-2022/p20/a2/hb@1",
        UnitId(SRC, PasalPath(pasal=20, ayat=2, huruf="b")),
    ),
    (
        "uu27-2022/p20/a2/hb/n1",
        "uu27-2022/p20/a2/hb/n1@1",
        UnitId(SRC, PasalPath(pasal=20, ayat=2, huruf="b", angka=1)),
    ),
    (
        "uu27-2022/p20/a2#pj",
        "uu27-2022/p20/a2#pj@1",
        UnitId(SRC, PasalPath(pasal=20, ayat=2), penjelasan=True),
    ),
    ("uu27-2022/pj-umum", "uu27-2022/pj-umum@1", UnitId(SRC, PjUmum())),
    (
        "uu27-2022/def/data-pribadi",
        "uu27-2022/def/data-pribadi@1",
        UnitId(SRC, DefinitionPath(slug="data-pribadi")),
    ),
    (
        "uu27-2022/obl/p20-01",
        "uu27-2022/obl/p20-01@1",
        UnitId(SRC, ObligationPath(pasal=20, seq=1)),
    ),
]


@pytest.mark.parametrize(("unit_str", "node_str", "unit"), EXAMPLES)
def test_fr_pdp_02_spec_examples_parse_and_format(
    unit_str: str, node_str: str, unit: UnitId
) -> None:
    assert ids.parse(unit_str) == unit
    assert ids.parse(node_str) == NodeId(unit, version=1)
    assert ids.format(unit) == unit_str
    assert ids.format(NodeId(unit, version=1)) == node_str


@pytest.mark.parametrize(
    "text",
    [
        "uu27-2022/p20/a2/n1",  # angka directly under ayat
        "uu27-2022/p20/hb",  # huruf directly under Pasal (grammar allows it)
        "uu27-2022/p20/n3",
        "uu27-2022/p20/a2/haa",  # double-letter huruf
        "uu27-2022/p20a/a1a/hb/n12",
        "pp-x-2025/bab12/bag3",
        "uu27-2022/obl/p20a-99",
        "uu27-2022/p20@12",
        "uu27-2022/def/data-pribadi-2",
    ],
)
def test_fr_pdp_02_other_valid_ids_round_trip(text: str) -> None:
    assert ids.format(ids.parse(text)) == text


@pytest.mark.parametrize(
    "text",
    [
        "",
        "uu27-2022",  # no path
        "/p20",  # no source
        "UU27-2022/p20",  # uppercase is rejected, never folded
        "uu27-2022/P20",
        "uu27-2022/p20/a2/hB",
        "uu27-2022/p0",  # ints start at 1
        "uu27-2022/p020",  # no leading zeros
        "uu27-2022/p20/a0",
        "uu27-2022/p20@0",
        "uu27-2022/p20@01",
        "uu27-2022/p20@",
        "uu27-2022/p20@1#pj",  # "#pj" must come before "@"
        "uu27-2022/p20/a2/hb/n0",
        "uu27-2022/p20ab",  # suffix is a single letter
        "uu27-2022/p20/h",  # huruf needs a letter
        "uu27-2022/bag1",  # Bagian only under a Bab
        "uu27-2022/bab3/par2",  # Paragraf only under a Bagian
        "uu27-2022/obl/p20-1",  # seq is two digits
        "uu27-2022/obl/p20-00",  # seq starts at 01
        "uu27-2022/def/",
        "uu27-2022/def/-data",
        "uu27-2022/def/data pribadi",
        "uu27-2022/x20",
        "uu27--2022/p20",
        "-uu27/p20",
        "uu27-2022/p20/",
        " uu27-2022/p20",
        "uu27-2022/p20 ",
        "uu27-2022/p20#PJ",
    ],
)
def test_fr_pdp_02_rejects_malformed_ids(text: str) -> None:
    with pytest.raises(InvalidIdError):
        ids.parse(text)


@pytest.mark.parametrize(
    "build",
    [
        lambda: PasalPath(pasal=0),
        lambda: PasalPath(pasal=1, pasal_suffix="ab"),
        lambda: PasalPath(pasal=1, ayat_suffix="a"),  # suffix without ayat
        lambda: PasalPath(pasal=1, huruf="B"),
        lambda: PasalPath(pasal=1, angka=0),
        lambda: Structure(bab=1, paragraf=1),
        lambda: ObligationPath(pasal=1, seq=100),
        lambda: DefinitionPath(slug="Data"),
        lambda: UnitId("UU27", PasalPath(pasal=1)),
        lambda: NodeId(UnitId("uu27-2022", PasalPath(pasal=1)), version=0),
    ],
)
def test_fr_pdp_02_constructors_reject_invalid_parts(build: object) -> None:
    with pytest.raises(InvalidIdError):
        build()  # type: ignore[operator]


@pytest.mark.parametrize(
    ("term", "slug"),
    [
        ("Data Pribadi", "data-pribadi"),
        ("Pengendali Data Pribadi", "pengendali-data-pribadi"),
        ("  Subjek   Data  Pribadi ", "subjek-data-pribadi"),
        ("Lembaga/Badan", "lembaga-badan"),
        ("Café Résumé", "cafe-resume"),
        ("Data--Pribadi!!", "data-pribadi"),
    ],
)
def test_fr_pdp_02_slugify(term: str, slug: str) -> None:
    assert ids.slugify(term) == slug


def test_fr_pdp_02_slugify_rejects_terms_without_letters_or_digits() -> None:
    with pytest.raises(InvalidIdError):
        ids.slugify("—")


def test_fr_pdp_02_assign_slugs_numbers_collisions_in_order() -> None:
    terms = ["Data Pribadi", "Data-Pribadi", "data pribadi", "Data Pribadi 2", "Orang"]
    assert ids.assign_slugs(terms) == [
        "data-pribadi",
        "data-pribadi-2",
        "data-pribadi-3",
        "data-pribadi-2-2",  # natural "-2" slug already taken by a collision
        "orang",
    ]


# --- property tests -------------------------------------------------------------

ints = st.integers(min_value=1, max_value=999)
letter = st.sampled_from("abcdefghijklmnopqrstuvwxyz")
opt_letter = st.none() | letter
sources = st.from_regex(r"[a-z0-9]{1,6}(-[a-z0-9]{1,6}){0,2}", fullmatch=True)
slugs = st.from_regex(r"[a-z0-9][a-z0-9-]{0,20}", fullmatch=True)


@st.composite
def pasal_paths(draw: st.DrawFn) -> PasalPath:
    ayat = draw(st.none() | ints)
    return PasalPath(
        pasal=draw(ints),
        pasal_suffix=draw(opt_letter),
        ayat=ayat,
        ayat_suffix=draw(opt_letter) if ayat is not None else None,
        huruf=draw(st.none() | st.text("abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=2)),
        angka=draw(st.none() | ints),
    )


@st.composite
def structures(draw: st.DrawFn) -> Structure:
    bagian = draw(st.none() | ints)
    paragraf = draw(st.none() | ints) if bagian is not None else None
    return Structure(bab=draw(ints), bagian=bagian, paragraf=paragraf)


paths = st.one_of(
    pasal_paths(),
    structures(),
    st.builds(DefinitionPath, slug=slugs),
    st.builds(ObligationPath, pasal=ints, pasal_suffix=opt_letter, seq=st.integers(1, 99)),
    st.just(PjUmum()),
)
units = st.builds(UnitId, source_id=sources, path=paths, penjelasan=st.booleans())
node_ids = st.builds(NodeId, unit=units, version=ints)


@given(st.one_of(units, node_ids))
def test_fr_pdp_02_round_trip_property(obj: UnitId | NodeId) -> None:
    text = ids.format(obj)
    assert ids.parse(text) == obj
    assert ids.format(ids.parse(text)) == text


@given(node_ids, st.data())
def test_fr_pdp_02_uppercasing_any_letter_is_rejected(node: NodeId, data: st.DataObject) -> None:
    text = ids.format(node)
    positions = [i for i, ch in enumerate(text) if ch.isalpha()]
    i = data.draw(st.sampled_from(positions))
    with pytest.raises(InvalidIdError):
        ids.parse(text[:i] + text[i].upper() + text[i + 1 :])
