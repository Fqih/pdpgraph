# SPDX-License-Identifier: Apache-2.0
"""Definitions, term usage and data categories on the real UU 27/2022 text (M1.4, FR-PDP-04).

Needs the verified raw files: `make ingest SOURCE=uu27-2022`, then `make test-snapshot`. Link
precision is measured on the owner-labeled sample (06 §2.10); these tests pin the extraction.
"""

from collections import Counter
from pathlib import Path

import pytest

from pdp_ingest.crosscheck import crosscheck, pdf_pages
from pdp_ingest.defs import (
    DataCategory,
    Definition,
    TermUse,
    data_categories,
    extract_definitions,
    link_terms,
)
from pdp_ingest.defs_review import defs_markdown, read_defs_reviews
from pdp_ingest.fetch import load_verified
from pdp_ingest.pipeline import segment_source
from pdp_ingest.refs import extract_refs
from pdp_ingest.registry import load_source
from pdp_ingest.segment import Unit

pytestmark = [pytest.mark.snapshot, pytest.mark.usefixtures("no_network")]

REPO = Path(__file__).resolve().parents[3]
S = "uu27-2022"
RAW = REPO / "data" / "raw"


@pytest.fixture(scope="module")
def units() -> list[Unit]:
    entry = load_source(S, REPO / "configs" / "sources")
    *_, units = segment_source(entry, raw_dir=RAW, overrides_dir=REPO / "data" / "overrides")
    return units


@pytest.fixture(scope="module")
def defs(units: list[Unit]) -> list[Definition]:
    return extract_definitions(units)


@pytest.fixture(scope="module")
def uses(units: list[Unit], defs: list[Definition]) -> list[TermUse]:
    return link_terms(units, defs, extract_refs(units))


@pytest.fixture(scope="module")
def categories(units: list[Unit]) -> list[DataCategory]:
    return data_categories(units, pasal="p4")


def test_all_pasal_1_definitions(defs: list[Definition]) -> None:
    assert [d.term for d in defs] == [
        "Data Pribadi",
        "Pelindungan Data Pribadi",
        "Informasi",
        "Pengendali Data Pribadi",
        "Prosesor Data Pribadi",
        "Subjek Data Pribadi",
        "Setiap Orang",
        "Korporasi",
        "Badan Publik",
        "Organisasi Internasional",
        "Pemerintah Pusat",
    ]
    assert [d.unit_id for d in defs] == [f"{S}/p1/n{i}" for i in range(1, 12)]
    assert defs[10].aliases == ("Pemerintah",)
    assert defs[10].node_id == f"{S}/def/pemerintah-pusat"
    assert all(len(d.aliases) == 0 for d in defs[:10])


def test_usage_counts(uses: list[TermUse]) -> None:
    assert Counter(u.kind for u in uses) == {"defined": 400, "informal": 15}
    occurrences = Counter((u.node_id.rsplit("/", 1)[1], u.kind) for u in uses for _ in u.spans)
    assert occurrences["data-pribadi", "defined"] == 208
    assert occurrences["pengendali-data-pribadi", "defined"] == 83
    assert occurrences["pemerintah-pusat", "defined"] == 3  # the others are "Peraturan Pemerintah"
    assert occurrences["subjek-data-pribadi", "informal"] == 1  # "subjek Data Pribadi", Pasal 1(2)


def test_longest_match_and_no_self_link(uses: list[TermUse]) -> None:
    n4 = {(u.node_id.rsplit("/", 1)[1], u.kind) for u in uses if u.unit_id == f"{S}/p1/n4"}
    assert ("pengendali-data-pribadi", "defined") not in n4
    assert ("data-pribadi", "defined") in n4  # "kendali pemrosesan Data Pribadi"
    p40 = {u.node_id.rsplit("/", 1)[1]: u.count for u in uses if u.unit_id == f"{S}/p40/a1"}
    assert p40 == {"pengendali-data-pribadi": 1, "data-pribadi": 2, "subjek-data-pribadi": 1}


def test_data_categories_from_pasal_4(categories: list[DataCategory]) -> None:
    assert [(c.code, c.parent_code) for c in categories] == [
        ("SPESIFIK", None),
        ("UMUM", None),
        ("KESEHATAN", "SPESIFIK"),
        ("BIOMETRIK", "SPESIFIK"),
        ("GENETIKA", "SPESIFIK"),
        ("CATATAN_KEJAHATAN", "SPESIFIK"),
        ("ANAK", "SPESIFIK"),
        ("KEUANGAN_PRIBADI", "SPESIFIK"),
        ("LAINNYA", "SPESIFIK"),
        ("NAMA_LENGKAP", "UMUM"),
        ("JENIS_KELAMIN", "UMUM"),
        ("KEWARGANEGARAAN", "UMUM"),
        ("AGAMA", "UMUM"),
        ("STATUS_PERKAWINAN", "UMUM"),
        ("DIKOMBINASIKAN_UNTUK_MENGIDENTIFIKASI_SESEORANG", "UMUM"),
    ]
    assert [c.code for c in categories if c.open] == ["LAINNYA"]


def test_committed_definitions_list_is_current(
    units: list[Unit],
    defs: list[Definition],
    uses: list[TermUse],
    categories: list[DataCategory],
) -> None:
    entry = load_source(S, REPO / "configs" / "sources")
    _, pdf = load_verified(entry, RAW)
    _, findings = crosscheck(units, pdf_pages(pdf))
    committed = (REPO / "data" / "review" / S / "definitions.md").read_text(encoding="utf-8")
    pages = {f.unit_id: f.pdf_page for f in findings}
    expected = defs_markdown(S, defs, uses, categories, units, read_defs_reviews(committed), pages)
    assert committed == expected
