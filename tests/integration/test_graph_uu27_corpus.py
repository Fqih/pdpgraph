# SPDX-License-Identifier: Apache-2.0
"""UU 27/2022 graph with its text: exact-text assertions (M1.5). Local only.

Needs the git-ignored stage artifacts (`make ingest SOURCE=uu27-2022`); skips without them.
"""

from datetime import date
from pathlib import Path

import pytest
from neo4j import Driver

from pdp_core.graph import definitions_for
from pdp_ingest.graph_load import ARTIFACTS, GraphData, graph_counts, load, read_graph

ROOT = Path(__file__).resolve().parents[2]
S = "uu27-2022"
PROCESSED = ROOT / "data" / "processed" / S

pytestmark = [
    pytest.mark.integration,
    pytest.mark.needs_corpus,
    pytest.mark.skipif(
        not all((PROCESSED / n).is_file() for n in ARTIFACTS),
        reason=f"no stage artifacts in {PROCESSED}; run `make ingest SOURCE={S}`",
    ),
]


@pytest.fixture(scope="module")
def data() -> GraphData:
    return read_graph(PROCESSED, ROOT / "data" / "review" / S)


@pytest.fixture(scope="module")
def driver(graph_driver: Driver, data: GraphData) -> Driver:
    load(graph_driver, data)
    return graph_driver


def test_graph_counts_equal_artifact_counts(driver: Driver, data: GraphData) -> None:
    expected = data.counts()
    actual = graph_counts(driver, S)
    wrong = {k: (v, actual.get(k)) for k, v in expected.items() if actual.get(k) != v}
    assert not wrong, f"count mismatch (expected, graph): {wrong}"


def test_unit_text_and_terms(driver: Driver) -> None:
    records, _, _ = driver.execute_query(
        "MATCH (u:LegalUnit {node_id: $n}) RETURN u.text AS text", n=f"{S}/p20/a1@1"
    )
    assert records[0]["text"] == (
        "Pengendali Data Pribadi wajib memiliki dasar pemrosesan Data Pribadi."
    )
    terms = [u.term for u in definitions_for(driver, [f"{S}/p40/a1@1"], date(2025, 1, 1))]
    assert terms == ["Data Pribadi", "Pengendali Data Pribadi", "Subjek Data Pribadi"]


def test_reference_mention_text(driver: Driver) -> None:
    records, _, _ = driver.execute_query(
        "MATCH (:LegalUnit {node_id: $a})-[r:REFERENCES]->(:LegalUnit {node_id: $b}) "
        "RETURN r.mention_text AS t",
        a=f"{S}/p14@1",
        b=f"{S}/p6@1",
    )
    assert records[0]["t"] == "sebagaimana dimaksud dalam Pasal 6 sampai dengan Pasal 11"
