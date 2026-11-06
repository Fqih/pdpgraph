# SPDX-License-Identifier: Apache-2.0
"""Graph rows from the stage artifacts (M1.5, FR-PDP-06); loading itself is an integration test."""

import hashlib
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from pdp_ingest.defs_review import CATEGORY_SECTION
from pdp_ingest.graph_load import ArtifactError, GraphData, read_graph
from pdp_ingest.graph_structure import export_structure, read_structure, write_structure
from pdp_ingest.review import Review

S = "s"
Artifacts = Callable[..., Path]  # conftest fixture `artifacts`


@pytest.fixture
def graph(artifacts: Artifacts) -> GraphData:
    root = artifacts({(CATEGORY_SECTION, "s/p2/a2/ha"): Review("faqih", "confirmed")})
    return read_graph(root / "processed" / S, root / "review" / S)


def test_source_provenance(graph: GraphData) -> None:
    (src,) = graph.sources
    assert src["source_id"] == S
    assert src["effective_from"] == date(2000, 1, 3)
    assert src["body_sha256"] == "a" * 64
    assert src["canonicalization_version"] == 1
    assert (src["segment_version"], src["refs_version"], src["defs_version"]) == (1, 1, 1)
    assert (src["overrides_total"], src["overrides_unconfirmed"]) == (2, 1)


def test_structures_and_units_are_version_1(graph: GraphData) -> None:
    assert [s["node_id"] for s in graph.structures] == ["s/bab1@1", "s/bab1/bag1@1", "s/bab2@1"]
    units = {u["unit_id"]: u for u in graph.units}
    p3 = units["s/p3"]
    assert p3["node_id"] == "s/p3@1"
    assert p3["version"] == 1
    assert p3["valid_from"] == date(2000, 1, 3)
    assert "valid_to" not in p3  # open: Neo4j stores no nulls
    assert p3["text_norm"].startswith("korporasi memproses data pribadi")
    assert units["s/p2/a1#pj"]["kind"] == "PENJELASAN"


def test_part_of_and_explained_by(graph: GraphData) -> None:
    part_of = {(r["child"], r["parent"]) for r in graph.part_of}
    assert ("s/bab1/bag1@1", "s/bab1@1") in part_of
    assert ("s/p1@1", "s/bab1/bag1@1") in part_of
    assert ("s/p2/a2/ha@1", "s/p2/a2@1") in part_of
    assert not any("#pj" in c or "pj-umum" in c for c, _ in part_of)
    assert all(isinstance(r["order"], int) for r in graph.part_of)
    explained = {(r["unit"], r["pj"]) for r in graph.explained_by}
    assert ("s/p2/a1@1", "s/p2/a1#pj@1") in explained
    assert not any("pj-umum" in pj for _, pj in explained)


def test_references_internal_targets_only(graph: GraphData) -> None:
    refs = {(r["from"], r["to"]): r for r in graph.references}
    assert set(refs) == {("s/p3@1", "s/p2/a1@1"), ("s/p2/a1#pj@1", "s/p3@1")}
    r = refs["s/p3@1", "s/p2/a1@1"]
    assert r["mention_text"] == "sebagaimana dimaksud dalam Pasal 2 ayat (1)"
    assert r["resolution"] == "EXACT"
    assert r["end"] - r["start"] == len(r["mention_text"])


def test_definitions_defines_and_uses_term(graph: GraphData) -> None:
    assert [d["node_id"] for d in graph.definitions] == [
        "s/def/data-pribadi@1",
        "s/def/korporasi@1",
    ]
    assert {(r["unit"], r["definition"]) for r in graph.defines} == {
        ("s/p1/n1@1", "s/def/data-pribadi@1"),
        ("s/p1/n2@1", "s/def/korporasi@1"),
    }
    uses = {(r["unit"], r["definition"]): r for r in graph.uses_term}
    korp = uses["s/p3@1", "s/def/korporasi@1"]
    assert (korp["count"], korp["informal_count"]) == (1, 1)  # "korporasi lain" is informal
    assert korp["ambiguous_case"] is True
    assert korp["nested_in_informal"] is False
    assert all(r["count"] > 0 for r in graph.uses_term)


def test_data_categories_parents_and_status(graph: GraphData) -> None:
    cats = {c["code"]: c for c in graph.categories}
    assert set(cats) == {"SPESIFIK", "UMUM", "ANAK"}
    assert cats["ANAK"]["status"] == "confirmed"
    assert cats["SPESIFIK"]["status"] == "proposed"
    assert graph.subcategory_of == [{"source_id": S, "code": "ANAK", "parent": "SPESIFIK"}]


def test_counts_cover_every_artifact_row(graph: GraphData) -> None:
    counts = graph.counts()
    assert counts["LegalUnit"] == len(graph.units)
    assert counts["REFERENCES"] == 2
    assert counts["USES_TERM"] == len(graph.uses_term)


def test_missing_artifact_is_an_error(artifacts: Artifacts) -> None:
    root = artifacts()
    (root / "processed" / S / "refs.jsonl").unlink()
    with pytest.raises(ArtifactError, match=r"refs\.jsonl"):
        read_graph(root / "processed" / S, root / "review" / S)


def test_source_manifest_is_json(artifacts: Artifacts) -> None:
    root = artifacts()
    assert json.loads((root / "processed" / S / "source.json").read_text())["source_id"] == S


def test_text_hashes_on_units_and_definitions(graph: GraphData) -> None:
    for row in graph.units + graph.definitions:
        assert row["text_sha256"] == hashlib.sha256(row["text"].encode("utf-8")).hexdigest()


def test_structure_export_has_no_text(graph: GraphData) -> None:
    exported = export_structure(graph)
    dumped = json.dumps(exported, ensure_ascii=False, default=str)
    for key in ('"text"', '"text_norm"', '"heading"', '"term"', '"aliases"', '"mention_text"'):
        assert key not in dumped
    assert "data tentang orang" not in dumped
    assert "Definisi" not in dumped  # a heading
    assert all("label" not in c and "explanation" not in c for c in exported["categories"])
    assert {u["node_id"]: u["text_sha256"] for u in exported["units"]}["s/p1/n1@1"] == (
        hashlib.sha256(b"Data Pribadi adalah data tentang orang.").hexdigest()
    )


def test_structure_round_trip(graph: GraphData, tmp_path: Path) -> None:
    path = tmp_path / "structure.json"
    write_structure(graph, path)
    first = path.read_bytes()
    back = read_structure(path)
    assert back.counts() == graph.counts()
    assert back.sources[0]["effective_from"] == date(2000, 1, 3)
    assert back.units[0]["valid_from"] == date(2000, 1, 3)
    assert export_structure(back) == export_structure(graph)
    write_structure(back, path)
    assert path.read_bytes() == first  # deterministic
