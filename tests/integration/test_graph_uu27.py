# SPDX-License-Identifier: Apache-2.0
"""The UU 27/2022 graph: ids, structure and canonical queries with hand-checked cases (M1.5,
FR-PDP-06). Runs in CI.

Built from the committed text-free structure artifact `tests/fixtures/uu27-2022/structure.json`
(text-less graph mode) in the Neo4j test instance. Text assertions are in
`test_graph_uu27_corpus.py` (local only); `test_structure_uu27.py` keeps the artifact current.
"""

from datetime import date
from pathlib import Path

import pytest
from neo4j import Driver

from pdp_core.graph import (
    Explanation,
    VersionError,
    context_of,
    definitions_for,
    expand_references,
    version_at,
)
from pdp_ingest.graph_load import GraphData, graph_counts, load
from pdp_ingest.graph_structure import read_structure

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
S = "uu27-2022"
STRUCTURE = ROOT / "tests" / "fixtures" / S / "structure.json"
DAY = date(2025, 1, 1)


def _n(*suffixes: str) -> tuple[str, ...]:
    return tuple(f"{S}/{s}@1" for s in suffixes)


@pytest.fixture(scope="module")
def data() -> GraphData:
    return read_structure(STRUCTURE)


@pytest.fixture(scope="module")
def driver(graph_driver: Driver, data: GraphData) -> Driver:
    load(graph_driver, data)
    return graph_driver


def test_graph_counts_equal_artifact_counts(driver: Driver, data: GraphData) -> None:
    expected = data.counts()
    actual = graph_counts(driver, S)
    wrong = {k: (v, actual.get(k)) for k, v in expected.items() if actual.get(k) != v}
    assert not wrong, f"count mismatch (expected, graph): {wrong}"


def test_units_are_text_less_with_hashes(driver: Driver) -> None:
    records, _, _ = driver.execute_query(
        "MATCH (u:LegalUnit)-[:IN_SOURCE]->(:Source {source_id: $s}) "
        "RETURN count(u.text) AS texts, count(u.text_sha256) AS hashes, count(u) AS units",
        s=S,
    )
    assert records[0].data() == {"texts": 0, "hashes": 519, "units": 519}


def test_counts_match_the_measured_source(data: GraphData) -> None:
    counts = data.counts()
    measured = {
        "LegalUnit": 519,
        "BAB": 16,
        "BAGIAN": 6,
        "REFERENCES": 146,
        "USES_TERM": 400,
        "Definition": 11,
        "DataCategory": 15,
    }
    wrong = {k: (v, counts[k]) for k, v in measured.items() if counts[k] != v}
    assert not wrong, f"artifact count changed (expected, artifacts): {wrong}"


def test_expand_references_from_pasal_57_1(driver: Driver) -> None:
    paths = expand_references(driver, list(_n("p57/a1")), DAY, max_hops=1)
    targets = [p[-1] for p in paths]
    assert len(targets) == 38
    assert targets[:5] == list(_n("p20/a1", "p21", "p24", "p25/a2", "p26/a3"))
    assert targets[-3:] == list(_n("p56/a2", "p56/a3", "p56/a4"))


def test_expand_references_from_pasal_14_range(driver: Driver) -> None:
    targets = [p[-1] for p in expand_references(driver, list(_n("p14")), DAY, max_hops=1)]
    assert targets == list(_n("p6", "p7", "p8", "p9", "p10", "p11"))


def test_definitions_for_unit_using_pengendali(driver: Driver) -> None:
    uses = definitions_for(driver, list(_n("p40/a1")), DAY)
    got = [(u.definition, u.defined_by, u.count) for u in uses]
    assert got == [
        (f"{S}/def/data-pribadi@1", f"{S}/p1/n1@1", 2),
        (f"{S}/def/pengendali-data-pribadi@1", f"{S}/p1/n4@1", 1),
        (f"{S}/def/subjek-data-pribadi@1", f"{S}/p1/n6@1", 1),
    ]
    assert all(u.term is None for u in uses)  # text-less graph


def test_context_of_pasal_20_2(driver: Driver) -> None:
    ctx = context_of(driver, f"{S}/p20/a2@1")
    assert ctx.pasal == f"{S}/p20@1"
    assert ctx.siblings == _n("p20/a1")
    # Pasal 20 ayat (2) has no Penjelasan of its own; its huruf do
    assert ctx.penjelasan == tuple(
        Explanation(n, "descendant_explanation") for n in _n(*(f"p20/a2/h{x}#pj" for x in "abcdef"))
    )


def test_version_at_returns_exactly_one(driver: Driver) -> None:
    assert version_at(driver, f"{S}/p20/a2", DAY) == f"{S}/p20/a2@1"
    with pytest.raises(VersionError, match="0 valid"):
        version_at(driver, f"{S}/p20/a2", date(2022, 10, 16))  # day before effective_from


def _snapshot(driver: Driver) -> tuple[list[object], list[object]]:
    nodes, _, _ = driver.execute_query(
        "MATCH (n)-[:IN_SOURCE]->(:Source {source_id: $s}) "
        "RETURN properties(n) AS p ORDER BY coalesce(n.node_id, n.code)",
        s=S,
    )
    edges, _, _ = driver.execute_query(
        "MATCH (a)-[:IN_SOURCE]->(:Source {source_id: $s}) MATCH (a)-[r]->(b) "
        "RETURN coalesce(a.node_id, a.code) AS a, type(r) AS t, properties(r) AS p, "
        "coalesce(b.node_id, b.code, b.source_id) AS b ORDER BY a, t, b, r.start",
        s=S,
    )
    return [r.data() for r in nodes], [r.data() for r in edges]


def test_rerun_is_identical(driver: Driver, data: GraphData) -> None:
    before = _snapshot(driver)
    load(driver, data)
    assert _snapshot(driver) == before
