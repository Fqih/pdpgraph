# SPDX-License-Identifier: Apache-2.0
"""load_graph and the canonical queries on a synthetic fixture graph (M1.5, FR-PDP-06).

Exact expected results, on the throwaway Neo4j test instance (`make up-test`, see conftest).
"""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from neo4j import Driver

from pdp_core.graph import (
    Explanation,
    VersionError,
    candidate_obligations,
    context_of,
    definitions_for,
    expand_references,
    version_at,
)
from pdp_ingest.canonical import blocks
from pdp_ingest.defs import data_categories, extract_definitions, link_terms
from pdp_ingest.defs_review import CATEGORY_SECTION, defs_markdown
from pdp_ingest.graph_load import GraphData, graph_counts, load, read_graph
from pdp_ingest.pipeline import write_graph_artifacts
from pdp_ingest.refs import extract_refs
from pdp_ingest.review import Review
from pdp_ingest.segment import segment

pytestmark = pytest.mark.integration

S = "fx-2000"
HTML = (
    "<p>BAB I</p><p>UMUM</p>"
    "<p>Pasal 1</p><p>Dalam Undang-Undang ini yang dimaksud dengan:</p><ol>"
    "<li><p>Data Uji adalah data untuk pengujian.</p></li>"
    "<li><p>Pengelola Data Uji adalah orang yang mengelola Data Uji.</p></li></ol>"
    "<p>BAB II</p><p>KEWAJIBAN</p><p>Bagian Kesatu</p><p>Umum</p>"
    "<p>Pasal 2</p><ol>"
    "<li><p>Pengelola Data Uji wajib melindungi Data Uji.</p></li>"
    "<li><p>Kewajiban sebagaimana dimaksud pada ayat (1) dikecualikan dalam hal:</p><ol>"
    "<li><p>keadaan darurat; atau</p></li><li><p>perintah pengadilan.</p></li></ol></li>"
    "<li><p>Ketentuan lebih lanjut diatur dalam Peraturan Pemerintah.</p></li></ol>"
    "<p>Pasal 3</p><p>Pelanggaran terhadap Pasal 2 ayat (2) dikenai sanksi.</p>"
    "<p>Pasal 4</p><ol>"
    "<li><p>Data Pribadi terdiri atas:</p><ol>"
    "<li><p>Data Pribadi yang bersifat khusus; dan</p></li>"
    "<li><p>Data Pribadi yang bersifat biasa.</p></li></ol></li>"
    "<li><p>Data Pribadi yang bersifat khusus meliputi:</p><ol>"
    "<li><p>data uji klinis; dan/atau</p></li>"
    "<li><p>data lainnya sesuai dengan ketentuan peraturan perundang-undangan.</p></li>"
    "</ol></li></ol>"
    "<p>PENJELASAN</p><p>I UMUM</p><p>Umum.</p><p>II PASAL DEMI PASAL</p>"
    "<p>Pasal 1</p><p>Cukup jelas.</p><p>Pasal 2</p><p>Ayat (1)</p><p>Cukup jelas.</p>"
    "<p>Ayat (2)</p><p>Keadaan darurat ditetapkan oleh Pengelola Data Uji.</p>"
    "<p>Ayat (3)</p><p>Cukup jelas.</p>"
    "<p>Pasal 3</p><p>Cukup jelas.</p><p>Pasal 4</p><p>Cukup jelas.</p>"
)
SOURCE = {
    "source_id": S,
    "title": "Undang-Undang Uji",
    "instrument_type": "UU",
    "number": 1,
    "year": 2000,
    "enacted_on": "2000-01-02",
    "promulgated_on": "2000-01-02",
    "effective_from": "2000-01-03",
    "url": "https://example.invalid/fx",
    "body_sha256": "b" * 64,
    "canonicalization_version": 1,
    "parser_version": "pdp_ingest@0.0.0",
    "segment_version": 1,
    "refs_version": 1,
    "defs_version": 1,
    "overrides_total": 0,
    "overrides_unconfirmed": 0,
}
DAY = date(2020, 1, 1)
CONFIRMED = ("fx-2000/p4/a1/ha", "fx-2000/p4/a2/ha", "fx-2000/p4/a2/hb")
ACTOR = "PENGELOLA_FX"


def _n(suffix: str) -> str:
    return f"{S}/{suffix}@1"


def _wipe(driver: Driver) -> None:
    driver.execute_query("MATCH (n)-[:IN_SOURCE]->(:Source {source_id: $s}) DETACH DELETE n", s=S)
    driver.execute_query("MATCH (n:Source {source_id: $s}) DETACH DELETE n", s=S)
    driver.execute_query("MATCH (n) WHERE n.fixture = $s DETACH DELETE n", s=S)


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> GraphData:
    root: Path = tmp_path_factory.mktemp("graph")
    seg = segment(S, blocks(HTML), explanation_marker="PENJELASAN")
    units = seg.units
    mentions = extract_refs(units)
    defs = extract_definitions(units)
    uses = link_terms(units, defs, mentions)
    cats = data_categories(units, pasal="p4")
    write_graph_artifacts(root / S, SOURCE, seg.structures, units, mentions, defs, uses, cats)
    reviews = {(CATEGORY_SECTION, u): Review("test", "confirmed") for u in CONFIRMED}
    review = root / "review" / "definitions.md"
    review.parent.mkdir()
    review.write_text(defs_markdown(S, defs, uses, cats, units, reviews), encoding="utf-8")
    return read_graph(root / S, root / "review")


@pytest.fixture(scope="module")
def driver(graph_driver: Driver, data: GraphData) -> Iterator[Driver]:
    _wipe(graph_driver)
    load(graph_driver, data, batch_size=3)  # small batches: several transactions per kind
    yield graph_driver
    _wipe(graph_driver)


def _snapshot(driver: Driver) -> tuple[list[object], list[object]]:
    nodes, _, _ = driver.execute_query(
        "MATCH (n)-[:IN_SOURCE]->(:Source {source_id: $s}) "
        "RETURN labels(n) AS l, properties(n) AS p ORDER BY coalesce(n.node_id, n.code)",
        s=S,
    )
    edges, _, _ = driver.execute_query(
        "MATCH (a)-[:IN_SOURCE]->(:Source {source_id: $s}) MATCH (a)-[r]->(b) "
        "RETURN coalesce(a.node_id, a.code) AS a, type(r) AS t, properties(r) AS p, "
        "coalesce(b.node_id, b.code, b.source_id) AS b ORDER BY a, t, b, r.start",
        s=S,
    )
    return [r.data() for r in nodes], [r.data() for r in edges]


def test_counts_match_artifacts(driver: Driver, data: GraphData) -> None:
    expected = data.counts()
    actual = graph_counts(driver, S)
    wrong = {k: (v, actual.get(k)) for k, v in expected.items() if actual.get(k) != v}
    assert not wrong, f"count mismatch (expected, graph): {wrong}"
    assert expected["REFERENCES"] == 2
    assert expected["SUBCATEGORY_OF"] == 2


def test_rerun_is_identical(driver: Driver, data: GraphData) -> None:
    before = _snapshot(driver)
    load(driver, data, batch_size=500)
    assert _snapshot(driver) == before


def test_units_carry_validity_and_source_provenance(driver: Driver) -> None:
    records, _, _ = driver.execute_query(
        "MATCH (u:LegalUnit {node_id: $n})-[:IN_SOURCE]->(s:Source) RETURN u, s", n=_n("p3")
    )
    u, s = records[0]["u"], records[0]["s"]
    assert u["valid_from"].to_native() == date(2000, 1, 3)
    assert u.get("valid_to") is None
    assert u["version"] == 1
    assert s["body_sha256"] == "b" * 64
    assert (s["overrides_total"], s["overrides_unconfirmed"]) == (0, 0)


def test_expand_references(driver: Driver) -> None:
    assert expand_references(driver, [_n("p3")], DAY, max_hops=1) == [(_n("p3"), _n("p2/a2"))]
    assert expand_references(driver, [_n("p3")], DAY, max_hops=2) == [
        (_n("p3"), _n("p2/a2")),
        (_n("p3"), _n("p2/a2"), _n("p2/a1")),
    ]
    assert expand_references(driver, [_n("p3")], date(1999, 1, 1)) == []  # before effective
    with pytest.raises(ValueError, match="max_hops"):
        expand_references(driver, [_n("p3")], DAY, max_hops=9)


def test_delegation_has_no_edge(driver: Driver) -> None:
    records, _, _ = driver.execute_query(
        "MATCH (u:LegalUnit {node_id: $n})-[r:REFERENCES]->() RETURN count(r) AS c",
        n=_n("p2/a3"),
    )
    assert records[0]["c"] == 0  # "diatur dalam Peraturan Pemerintah"


def test_definitions_for(driver: Driver) -> None:
    got = [
        (d.definition, d.defined_by, d.count) for d in definitions_for(driver, [_n("p2/a1")], DAY)
    ]
    assert got == [
        (_n("def/data-uji"), _n("p1/n1"), 1),
        (_n("def/pengelola-data-uji"), _n("p1/n2"), 1),
    ]
    (pj,) = definitions_for(driver, [_n("p2/a2#pj")], DAY)
    assert (pj.term, pj.ambiguous_case) == ("Pengelola Data Uji", False)


def test_context_of(driver: Driver) -> None:
    ctx = context_of(driver, _n("p2/a2/ha"))
    assert ctx.pasal == _n("p2")
    assert ctx.siblings == (_n("p2/a2/hb"),)
    assert ctx.penjelasan == (Explanation(_n("p2/a2#pj"), "ancestor_explanation"),)
    ayat = context_of(driver, _n("p2/a2"))
    assert ayat.siblings == (_n("p2/a1"), _n("p2/a3"))
    assert ayat.penjelasan == (Explanation(_n("p2/a2#pj"), "own_explanation"),)
    pasal = context_of(driver, _n("p2"))
    assert [(e.node_id, e.relation) for e in pasal.penjelasan] == [
        (_n("p2/a1#pj"), "descendant_explanation"),
        (_n("p2/a2#pj"), "descendant_explanation"),
        (_n("p2/a3#pj"), "descendant_explanation"),
    ]
    with pytest.raises(KeyError):
        context_of(driver, _n("p99"))


def test_version_at_returns_exactly_one(driver: Driver) -> None:
    assert version_at(driver, f"{S}/p2/a1", DAY) == _n("p2/a1")
    with pytest.raises(VersionError, match="0 valid"):
        version_at(driver, f"{S}/p2/a1", date(1999, 1, 1))
    driver.execute_query(  # a second version with an overlapping validity: must be refused
        "MATCH (s:Source {source_id: $s}) CREATE (v:LegalUnit {node_id: $id, unit_id: $u, "
        "valid_from: date('2010-01-01'), version: 2})-[:IN_SOURCE]->(s)",
        s=S,
        id=f"{S}/p2/a1@2",
        u=f"{S}/p2/a1",
    )
    try:
        with pytest.raises(VersionError, match="2 valid"):
            version_at(driver, f"{S}/p2/a1", DAY)
        assert version_at(driver, f"{S}/p2/a1", date(2005, 1, 1)) == _n("p2/a1")
    finally:
        driver.execute_query(
            "MATCH (v:LegalUnit {node_id: $id}) DETACH DELETE v", id=f"{S}/p2/a1@2"
        )


def test_candidate_obligations_and_unknown_categories(driver: Driver) -> None:
    driver.execute_query(
        """
        CREATE (a:Actor {name: $actor, fixture: $s})
        WITH a
        MATCH (lu:LegalUnit {node_id: $unit}), (k:DataCategory {code: 'KHUSUS'}),
              (c:DataCategory {code: 'UJI_KLINIS'})
        CREATE (lu)-[:IMPOSES]->(o1:Obligation {node_id: $o1, review_status: 'APPROVED',
                                                fixture: $s})-[:APPLIES_TO_ACTOR]->(a)
        CREATE (lu)-[:IMPOSES]->(o2:Obligation {node_id: $o2, review_status: 'APPROVED',
                                                fixture: $s})-[:APPLIES_TO_ACTOR]->(a)
        CREATE (o2)-[:TRIGGERED_BY]->(k)
        CREATE (lu)-[:IMPOSES]->(o3:Obligation {node_id: $o3, review_status: 'APPROVED',
                                                fixture: $s})-[:APPLIES_TO_ACTOR]->(a)
        CREATE (o3)-[:TRIGGERED_BY]->(c)
        CREATE (lu)-[:IMPOSES]->(o4:Obligation {node_id: $o4, review_status: 'PENDING',
                                                fixture: $s})-[:APPLIES_TO_ACTOR]->(a)
        """,
        actor=ACTOR,
        s=S,
        unit=_n("p2/a1"),
        o1=f"{S}/obl/p2-01@1",
        o2=f"{S}/obl/p2-02@1",
        o3=f"{S}/obl/p2-03@1",
        o4=f"{S}/obl/p2-04@1",
    )
    plain = candidate_obligations(driver, ACTOR, [], [], DAY)
    assert plain.obligations == (f"{S}/obl/p2-01@1",)  # unconditional only; PENDING never
    member = candidate_obligations(driver, ACTOR, ["UJI_KLINIS"], [], DAY)
    assert member.obligations == (f"{S}/obl/p2-01@1", f"{S}/obl/p2-02@1", f"{S}/obl/p2-03@1")
    assert member.unknown_categories == ()
    odd = candidate_obligations(driver, ACTOR, ["LAINNYA", "BIASA", "NOT_A_CODE"], [], DAY)
    # LAINNYA is open-ended, BIASA is only proposed, NOT_A_CODE does not exist: all UNKNOWN,
    # none mapped to the nearest code
    assert odd.unknown_categories == ("BIASA", "LAINNYA", "NOT_A_CODE")
    assert odd.obligations == (f"{S}/obl/p2-01@1",)
