# SPDX-License-Identifier: Apache-2.0
"""`index` stage documents, embedding guard and multi-vector cache (M1.6, FR-PDP-07)."""

from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest

from pdp_ingest.index import (
    EmbeddingMixError,
    MultiVectors,
    build_documents,
    check_embedding,
    multivector_path,
    read_multivectors,
    with_embeddings,
    write_multivectors,
)

S = "s"
Artifacts = Callable[..., Path]  # conftest fixture `artifacts`
REV = "a" * 40


@pytest.fixture
def docs(artifacts: Artifacts) -> dict[str, dict[str, object]]:
    root = artifacts()
    return {d["unit_id"]: d for d in build_documents(root / "processed" / S)}


def test_one_document_per_citable_unit(docs: dict[str, dict[str, object]]) -> None:
    units = ("p1", "p1/n1", "p1/n2", "p2/a1", "p2/a1/ha", "p2/a1/hb", "p2/a2", "p2/a2/ha", "p3")
    explanations = ("pj-umum", "p2/a1#pj")  # substantive only; "Cukup jelas." is not indexed
    assert sorted(docs) == sorted(f"s/{u}" for u in units + explanations)  # no Pasal with ayat


def test_penjelasan_documents(docs: dict[str, dict[str, object]]) -> None:
    pj = docs["s/p2/a1#pj"]
    assert pj["kind"] == "PENJELASAN"
    assert pj["explains"] == "s/p2/a1"
    assert pj["text"] == "Lihat Pasal 3."
    assert pj["penjelasan_text"] == ""  # it is the Penjelasan
    assert pj["context_text"] == (
        "JENIS / Data Pribadi terdiri atas: / Pasal 2 ayat (1) / Penjelasan Pasal 2 ayat (1)"
    )
    assert pj["embedding_input"] == "Data Pribadi terdiri atas: Lihat Pasal 3."
    assert docs["s/p2/a1"]["penjelasan_text"] == "Lihat Pasal 3."  # kept on the parent too
    assert "explains" not in docs["s/p2/a1"]
    umum = docs["s/pj-umum"]
    assert "explains" not in umum  # explains no single unit
    assert umum["context_text"] == "Penjelasan Umum"


def test_document_fields(docs: dict[str, dict[str, object]]) -> None:
    d = docs["s/p2/a1/ha"]
    assert d["node_id"] == "s/p2/a1/ha@1"
    assert d["source_id"] == S
    assert d["kind"] == "HURUF"
    assert d["label"] == "Pasal 2 ayat (1) huruf a"
    assert d["text"] == "Data Pribadi yang bersifat spesifik; dan"
    # structure headings, ancestor lead-ins, then the label
    assert d["context_text"] == "JENIS / Data Pribadi terdiri atas: / Pasal 2 ayat (1) huruf a"
    assert d["penjelasan_text"] == "Lihat Pasal 3."  # the ayat's; "Cukup jelas." is dropped
    assert d["terms"] == ["data pribadi"]
    assert d["concepts"] == []
    assert d["valid_from"] == date(2000, 1, 3)
    assert "valid_to" not in d
    assert (
        d["embedding_input"]
        == "Data Pribadi terdiri atas: Data Pribadi yang bersifat spesifik; dan"
    )


def test_pasal_without_ayat_and_definitions(docs: dict[str, dict[str, object]]) -> None:
    assert docs["s/p1/n1"]["context_text"] == (
        "UMUM / Definisi / Dalam Undang-Undang ini yang dimaksud dengan: / Pasal 1 angka 1"
    )
    assert docs["s/p1/n2"]["terms"] == []  # defines Korporasi, uses no other term
    assert docs["s/p3"]["penjelasan_text"] == ""
    assert docs["s/p3"]["terms"] == ["data pribadi", "korporasi"]


def test_with_embeddings_adds_model_fields(docs: dict[str, dict[str, object]]) -> None:
    rows = list(docs.values())[:2]
    out = with_embeddings(rows, [[1.0, 0.0], [0.0, 1.0]], model="m/x", revision=REV)
    assert [r["embedding"] for r in out] == [[1.0, 0.0], [0.0, 1.0]]
    assert all(r["embedding_model"] == "m/x" and r["embedding_revision"] == REV for r in out)
    assert all("embedding_input" not in r for r in out)
    assert "embedding" not in rows[0]  # inputs are not mutated


def test_check_embedding_refuses_mixed_models() -> None:
    meta = {"embedding_model": "m/x", "embedding_revision": REV, "embedding_dim": 2}
    check_embedding(meta, model="m/x", revision=REV, dim=2)
    with pytest.raises(EmbeddingMixError, match="embedding_revision"):
        check_embedding(meta, model="m/x", revision="b" * 40, dim=2)
    with pytest.raises(EmbeddingMixError, match="embedding_model"):
        check_embedding(meta, model="m/y", revision=REV, dim=2)


def test_multivector_cache_round_trip(tmp_path: Path) -> None:
    path = multivector_path(tmp_path, "BAAI/bge-m3", REV)
    assert path == tmp_path / "multivectors" / "BAAI--bge-m3@aaaaaaaaaaaa.jsonl"
    rows = [
        MultiVectors("s/p1@1", "BAAI/bge-m3", REV, [[0.5, -0.25], [1.0, 0.0]]),
        MultiVectors("s/p3@1", "BAAI/bge-m3", REV, [[0.125, 0.75]]),
    ]
    write_multivectors(path, rows)
    back = read_multivectors(path)
    assert back == {r.node_id: r for r in rows}  # values exact in float16
    with pytest.raises(EmbeddingMixError, match="revision"):
        write_multivectors(path, [MultiVectors("s/p1@1", "BAAI/bge-m3", "b" * 40, [[0.0]])])
