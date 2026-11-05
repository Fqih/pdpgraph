# SPDX-License-Identifier: Apache-2.0
"""Canonical form of the law body (canonicalization v1) and its content invariants (M1.1)."""

import pytest

from pdp_ingest.canonical import (
    CANONICALIZATION_VERSION,
    EXTRACTION_METHOD,
    ContentInvariants,
    InvariantError,
    blocks,
    canonical_sha256,
    canonical_text,
    check_invariants,
)

HTML = (
    "<p><strong>UNDANG-UNDANG</strong></p>\n<p> </p>"
    '<p style="text-align:center"><strong>BAB I</strong></p>'
    "<p><strong>Pasal 1</strong></p><ol><li><p>Data Pribadi terdiri atas:</p>"
    "<ol><li><p>spesifik;</p></li><li><p>umum.</p></li></ol></li></ol>"
    '<p style="font-weight:bold">Pasal 2 <span class="popup-content"></span></p>'
    "<p>Lihat <span class='v_c_link'>Pasal 1</span> dan&nbsp;&nbsp;Pasal&#160;2.</p>"
    "<p>PENJELASAN</p><p>Pasal 1</p><p>Cukup jelas.</p><p>Pasal 2</p><p>Cukup jelas.</p>"
)

INVARIANTS = ContentInvariants(
    starts_with=["UNDANG-UNDANG"],
    ends_with=["Pasal 2", "Cukup jelas."],
    explanation_marker="PENJELASAN",
    pasal_headings=2,
    bab_headings=1,
    cukup_jelas=2,
    items=[{"pasal": 1, "path": [1, 2], "text": "umum."}],
)


def test_version_constants() -> None:
    assert CANONICALIZATION_VERSION == 1
    assert EXTRACTION_METHOD == "html-element-blocks"


def test_blocks_are_nfc_whitespace_collapsed_with_list_paths() -> None:
    got = [(b.text, b.path) for b in blocks(HTML)]
    assert got[:6] == [
        ("UNDANG-UNDANG", ()),
        ("BAB I", ()),
        ("Pasal 1", ()),
        ("Data Pribadi terdiri atas:", (1,)),
        ("spesifik;", (1, 1)),
        ("umum.", (1, 2)),
    ]
    assert ("Pasal 2", ()) in got  # empty popup span does not change the heading
    assert ("Lihat Pasal 1 dan Pasal 2.", ()) in got  # inline refs stay inline; nbsp collapsed


def test_canonical_text_keeps_list_structure_tokens() -> None:
    lines = canonical_text(HTML).split("\n")
    assert lines[2:10] == [
        "Pasal 1",
        "[ol]",
        "[li] Data Pribadi terdiri atas:",
        "[ol]",
        "[li] spesifik;",
        "[li] umum.",
        "[/ol]",
        "[/ol]",
    ]


@pytest.mark.parametrize(
    "variant",
    [
        HTML.replace("<p> </p>", ""),  # empty blocks
        HTML.replace("<p>", '<p style="margin:0px;">'),  # attributes
        HTML.replace("</p><", "</p>\n  \n<"),  # inter-tag whitespace
        HTML.replace("<strong>BAB I</strong>", "<b>BAB  I</b>"),  # inline markup, spacing
        HTML.replace("&nbsp;", "\u00a0"),  # entity vs literal
    ],
)
def test_hash_ignores_serialization_changes(variant: str) -> None:
    assert canonical_sha256(variant) == canonical_sha256(HTML)


def test_nfc_normalization() -> None:
    assert canonical_sha256("<p>e\u0301</p>") == canonical_sha256("<p>\u00e9</p>")


def test_br_breaks_a_line_in_any_spelling() -> None:
    assert canonical_text("<p>a<br>b</p>") == canonical_text("<p>a<br />b</p>") == "a\nb"


@pytest.mark.parametrize(
    "variant",
    [
        HTML.replace("umum.", "umum;"),  # text
        HTML.replace("<ol><li><p>spesifik;", "<ol><li><p>x</p></li><li><p>spesifik;"),  # list
        HTML.replace("<p>Lihat", "<p>Lihat</p><p>"),  # block boundary
    ],
)
def test_hash_changes_with_content_or_structure(variant: str) -> None:
    assert canonical_sha256(variant) != canonical_sha256(HTML)


def test_invariants_pass_on_conforming_body() -> None:
    report = check_invariants(blocks(HTML), INVARIANTS)
    assert report == {
        "starts_with": "ok",
        "ends_with": "ok",
        "bab_headings": 1,
        "pasal_headings_body": 2,
        "pasal_headings_explanation": 2,
        "cukup_jelas": 2,
        "items": ["Pasal 1 path [1, 2] = 'umum.'"],
    }


@pytest.mark.parametrize(
    ("html", "message"),
    [
        (HTML.replace("UNDANG-UNDANG", "PERATURAN"), "starts_with"),
        (HTML.replace("<p>Pasal 2</p><p>Cukup jelas.</p>", ""), "ends_with"),
        (HTML.replace("PENJELASAN", "Penjelasan umum"), "explanation marker"),
        (HTML.replace("<strong>Pasal 1</strong>", "<strong>Pasal 3</strong>"), r"Pasal headings"),
        (HTML.replace(">BAB I<", ">BAB II<"), "BAB headings"),
        (HTML.replace("<p>Cukup jelas.</p><p>Pasal 2", "<p>Pasal 2"), "Cukup jelas"),
        (HTML.replace("umum.", "umum"), "Pasal 1 path"),
    ],
)
def test_each_invariant_catches_its_violation(html: str, message: str) -> None:
    with pytest.raises(InvariantError, match=message):
        check_invariants(blocks(html), INVARIANTS)


def test_cukup_jelas_counts_a_block_missing_its_final_period() -> None:
    # The Komdigi page drops the period once (Penjelasan Pasal 46 ayat 2); still one occurrence.
    html = HTML.replace("<p>Cukup jelas.</p><p>Pasal 2", "<p>Cukup jelas</p><p>Pasal 2")
    assert check_invariants(blocks(html), INVARIANTS)["cukup_jelas"] == 2
