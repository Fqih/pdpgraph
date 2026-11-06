# SPDX-License-Identifier: Apache-2.0
"""`legal_units` index body and query bodies (M1.6, FR-PDP-07). No OpenSearch needed."""

import json
from datetime import date
from pathlib import Path

import pytest

from pdp_core.search import (
    ACTORS,
    ALIAS,
    FIELDS,
    bm25_body,
    index_body,
    index_name,
    knn_body,
    protected_keywords,
    rrf,
)

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT = ROOT / "tests" / "fixtures" / "uu27-2022" / "legal_units_v1.index.json"
DAY = date(2025, 1, 1)


def test_names() -> None:
    assert ALIAS == "legal_units"
    assert index_name() == "legal_units_v1"
    assert index_name(2, prefix="itest-") == "itest-legal_units_v2"


def test_protected_keywords_are_lowercase_term_and_actor_words() -> None:
    words = protected_keywords(["Pengendali Data Pribadi", "Setiap Orang"])
    assert words == sorted(set(words))
    assert {"pengendali", "data", "pribadi", "setiap", "orang"} <= set(words)
    assert {"prosesor", "subjek", "lembaga", "pihak", "ketiga"} <= set(words)  # actors
    assert "PENGENDALI" in ACTORS


def test_index_body_fields_and_meta() -> None:
    body = index_body(["pribadi"], model="m/x", revision="a" * 40, dim=4)
    props = body["mappings"]["properties"]
    assert body["mappings"]["dynamic"] == "strict"
    assert body["mappings"]["_meta"] == {
        "embedding_model": "m/x",
        "embedding_revision": "a" * 40,
        "embedding_dim": 4,
        "index_version": 1,
    }
    assert props["text"]["analyzer"] == "legal_plain"
    assert props["text"]["fields"]["stem"]["analyzer"] == "legal_stem"
    assert props["text"]["fields"]["shingle"]["analyzer"] == "legal_shingle"
    for f in ("context_text", "penjelasan_text"):
        assert props[f]["type"] == "text"
    for f in ("node_id", "unit_id", "source_id", "kind", "label", "terms", "concepts"):
        assert props[f]["type"] == "keyword"
    assert props["valid_from"]["type"] == props["valid_to"]["type"] == "date"
    assert props["embedding"]["type"] == "knn_vector"
    assert props["embedding"]["dimension"] == 4
    assert props["embedding_model"]["type"] == props["embedding_revision"]["type"] == "keyword"
    analysis = body["settings"]["analysis"]
    assert analysis["filter"]["protected_terms"] == {
        "type": "keyword_marker",
        "keywords": ["pribadi"],
        "ignore_case": True,
    }
    stem = analysis["analyzer"]["legal_stem"]["filter"]
    assert stem.index("protected_terms") < stem.index("indonesian_stemmer")
    assert analysis["analyzer"]["legal_plain"]["filter"] == ["lowercase"]


def test_index_body_equals_committed_snapshot() -> None:
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    keywords = snapshot["settings"]["analysis"]["filter"]["protected_terms"]["keywords"]
    meta = snapshot["mappings"]["_meta"]
    body = index_body(
        keywords,
        model=meta["embedding_model"],
        revision=meta["embedding_revision"],
        dim=meta["embedding_dim"],
    )
    assert body == snapshot


def test_bm25_body_filters_validity() -> None:
    body = bm25_body("hak subjek", FIELDS["multi_field"], DAY, k=7)
    assert body["size"] == 7
    query = body["query"]["bool"]
    assert query["must"][0]["multi_match"]["query"] == "hak subjek"
    assert query["must"][0]["multi_match"]["fields"] == FIELDS["multi_field"]
    assert {"range": {"valid_from": {"lte": "2025-01-01"}}} in query["filter"]
    assert query["filter"][1] == {
        "bool": {
            "should": [
                {"bool": {"must_not": {"exists": {"field": "valid_to"}}}},
                {"range": {"valid_to": {"gt": "2025-01-01"}}},
            ],
            "minimum_should_match": 1,
        }
    }


def test_field_sets() -> None:
    assert FIELDS["bm25_plain"] == ["text"]
    assert FIELDS["bm25_stem"] == ["text.stem"]
    assert "text.shingle" in FIELDS["multi_field"]
    assert "penjelasan_text^0.5" in FIELDS["multi_field"]


def test_knn_body() -> None:
    body = knn_body([0.1, 0.2], DAY, k=5)
    knn = body["query"]["knn"]["embedding"]
    assert knn["vector"] == [0.1, 0.2]
    assert knn["k"] == 5
    assert knn["filter"]["bool"]["filter"][0] == {"range": {"valid_from": {"lte": "2025-01-01"}}}
    assert body["size"] == 5


def test_rrf_fuses_by_reciprocal_rank() -> None:
    fused = rrf([["a", "b", "c"], ["c", "a", "d"]], k=60)
    # a: 1/61 + 1/62; c: 1/63 + 1/61; b: 1/62; d: 1/63
    assert fused == ["a", "c", "b", "d"]


def test_rrf_ties_keep_first_seen_order() -> None:
    assert rrf([["x"], ["y"]]) == ["x", "y"]


@pytest.mark.parametrize("k", [0, -1])
def test_rrf_needs_positive_k(k: int) -> None:
    with pytest.raises(ValueError, match="k"):
        rrf([["a"]], k=k)
