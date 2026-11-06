# SPDX-License-Identifier: Apache-2.0
"""The UU 27/2022 graph against its artifacts, and canonical queries with hand-checked cases
(M1.5, FR-PDP-06).

Needs `make up` and the stage artifacts of `make ingest SOURCE=uu27-2022` (git-ignored, so the
tests skip without them). Loading is idempotent, so the tests (re)load the source first.
"""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from neo4j import Driver

from pdp_core.graph import (
    VersionError,
    connect,
    context_of,
    definitions_for,
    expand_references,
    version_at,
)
from pdp_ingest.graph_load import ARTIFACTS, GraphData, graph_counts, load, read_graph

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
S = "uu27-2022"
PROCESSED = ROOT / "data" / "processed" / S
DAY = date(2025, 1, 1)

if not all((PROCESSED / name).is_file() for name in ARTIFACTS):
    pytest.skip(
        f"no stage artifacts in {PROCESSED}; run `make ingest SOURCE={S}`", allow_module_level=True
    )


def _n(*suffixes: str) -> tuple[str, ...]:
    return tuple(f"{S}/{s}@1" for s in suffixes)


@pytest.fixture(scope="module")
def data() -> GraphData:
    return read_graph(PROCESSED, ROOT / "data" / "review" / S)


@pytest.fixture(scope="module")
def driver(data: GraphData) -> Iterator[Driver]:
    with connect() as d:
        load(d, data)
        yield d


def test_graph_counts_equal_artifact_counts(driver: Driver, data: GraphData) -> None:
    expected = data.counts()
    actual = graph_counts(driver, S)
    wrong = {k: (v, actual.get(k)) for k, v in expected.items() if actual.get(k) != v}
    assert not wrong, f"count mismatch (expected, graph): {wrong}"


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
    got = [
        (u.term, u.defined_by, u.count) for u in definitions_for(driver, list(_n("p40/a1")), DAY)
    ]
    assert got == [
        ("Data Pribadi", f"{S}/p1/n1@1", 2),
        ("Pengendali Data Pribadi", f"{S}/p1/n4@1", 1),
        ("Subjek Data Pribadi", f"{S}/p1/n6@1", 1),
    ]


def test_context_of_pasal_20_2(driver: Driver) -> None:
    ctx = context_of(driver, f"{S}/p20/a2@1")
    assert ctx.pasal == f"{S}/p20@1"
    assert ctx.siblings == _n("p20/a1")
    # Pasal 20 ayat (2) has no Penjelasan of its own; its huruf do
    assert ctx.penjelasan == _n(*(f"p20/a2/h{x}#pj" for x in "abcdef"))


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
