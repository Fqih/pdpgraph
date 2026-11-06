# SPDX-License-Identifier: Apache-2.0
"""`legal_units` index in OpenSearch: mapping, protected terms, alias swap, model guard, queries
(M1.6, FR-PDP-07). Needs `make up`.

Every index and alias here has a per-session `itest-<hex>-` prefix and is deleted afterwards,
so the dev `legal_units` alias and its indexes are never touched.
"""

import json
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import httpx
import pytest

from pdp_core.search import (
    ALIAS,
    FIELDS,
    EmbeddingMixError,
    SearchSettings,
    alias_targets,
    analyze,
    bm25_body,
    bulk,
    ensure_index,
    index_body,
    index_name,
    knn_body,
    search_ids,
    swap_alias,
)

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "tests" / "fixtures" / "uu27-2022" / "legal_units_v1.index.json"
REV = "a" * 40
DAY = date(2025, 1, 1)


@pytest.fixture(scope="module")
def http() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=SearchSettings().opensearch_url, timeout=30) as c:
        try:
            c.get("/").raise_for_status()
        except httpx.HTTPError:
            pytest.fail("OpenSearch is not reachable; run `make up`")
        yield c


@pytest.fixture
def prefix(http: httpx.Client) -> Iterator[str]:
    p = f"itest-{uuid.uuid4().hex[:8]}-"
    yield p
    http.delete(f"/{p}*")


def _snapshot() -> dict[str, object]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_mapping_is_stored_as_built(http: httpx.Client, prefix: str) -> None:
    body = index_body(["pribadi"], model="m/x", revision=REV, dim=4)
    name = index_name(prefix=prefix)
    ensure_index(http, name, body)
    stored = http.get(f"/{name}/_mapping").json()[name]["mappings"]
    assert stored["_meta"] == body["mappings"]["_meta"]
    assert stored["dynamic"] == "strict"
    assert stored["properties"]["text"] == body["mappings"]["properties"]["text"]
    assert stored["properties"]["embedding"]["dimension"] == 4
    assert set(stored["properties"]) == set(body["mappings"]["properties"])


def test_protected_terms_stay_intact_in_text_stem(http: httpx.Client, prefix: str) -> None:
    name = index_name(prefix=prefix)
    ensure_index(http, name, _snapshot())
    text = "Pengendali Data Pribadi dan Prosesor Data Pribadi"
    assert analyze(http, name, "text.stem", text) == [
        "pengendali",
        "data",
        "pribadi",
        "dan",
        "prosesor",
        "data",
        "pribadi",
    ]
    # ordinary words still stem
    stemmed = analyze(http, name, "text.stem", "kewajiban memproses permintaan")
    assert stemmed == ["wajib", "proses", "minta"]
    # the same stemmer without the marker cuts them ("prosesor" it leaves alone anyway)
    bare = http.post(
        "/_analyze",
        json={
            "tokenizer": "standard",
            "filter": ["lowercase", {"type": "stemmer", "language": "indonesian"}],
            "text": "Pengendali Pribadi Prosesor",
        },
    ).json()
    assert [t["token"] for t in bare["tokens"]] == ["endali", "pribad", "prosesor"]
    assert analyze(http, name, "text", "Pengendali Data Pribadi") == [
        "pengendali",
        "data",
        "pribadi",
    ]


def test_alias_swap_is_atomic(http: httpx.Client, prefix: str) -> None:
    v1, v2 = index_name(1, prefix=prefix), index_name(2, prefix=prefix)
    alias = prefix + ALIAS
    body = index_body([], model="m/x", revision=REV, dim=2)
    ensure_index(http, v1, body)
    ensure_index(http, v2, body)
    assert swap_alias(http, alias, v1) == []
    assert alias_targets(http, alias) == [v1]
    assert swap_alias(http, alias, v2) == [v1]
    assert alias_targets(http, alias) == [v2]


def test_index_refuses_another_embedding_model(http: httpx.Client, prefix: str) -> None:
    name = index_name(prefix=prefix)
    ensure_index(http, name, index_body([], model="m/x", revision=REV, dim=2))
    ensure_index(http, name, index_body([], model="m/x", revision=REV, dim=2))  # same: fine
    with pytest.raises(EmbeddingMixError, match="embedding_revision"):
        ensure_index(http, name, index_body([], model="m/x", revision="b" * 40, dim=2))


def _doc(unit: str, text: str, vector: list[float], valid_from: str) -> dict[str, object]:
    return {
        "node_id": f"t/{unit}@1",
        "unit_id": f"t/{unit}",
        "source_id": "t",
        "kind": "AYAT",
        "label": unit,
        "text": text,
        "context_text": "",
        "penjelasan_text": "",
        "terms": [],
        "concepts": [],
        "valid_from": valid_from,
        "embedding": vector,
        "embedding_model": "m/x",
        "embedding_revision": REV,
    }


def test_bm25_knn_and_validity(http: httpx.Client, prefix: str) -> None:
    name = index_name(prefix=prefix)
    meta = index_body(["pribadi"], model="m/x", revision=REV, dim=2)
    ensure_index(http, name, meta)
    bulk(
        http,
        name,
        [
            _doc("a1", "Pengendali wajib memproses data", [1.0, 0.0], "2022-10-17"),
            _doc("a2", "Subjek berhak meminta salinan", [0.0, 1.0], "2022-10-17"),
            _doc("a3", "Pengendali wajib memproses ulang", [1.0, 0.1], "2030-01-01"),
        ],
    )
    assert search_ids(http, name, bm25_body("proses", FIELDS["bm25_stem"], DAY, k=5)) == ["t/a1"]
    assert search_ids(http, name, bm25_body("proses", FIELDS["bm25_plain"], DAY, k=5)) == []
    assert search_ids(http, name, knn_body([0.0, 1.0], DAY, k=2))[0] == "t/a2"
    assert "t/a3" not in search_ids(http, name, knn_body([1.0, 0.1], DAY, k=3))


def test_bulk_refuses_documents_of_another_model(http: httpx.Client, prefix: str) -> None:
    name = index_name(prefix=prefix)
    ensure_index(http, name, index_body([], model="m/x", revision=REV, dim=2))
    doc = _doc("a1", "x", [1.0, 0.0], "2022-10-17") | {"embedding_revision": "b" * 40}
    with pytest.raises(EmbeddingMixError, match="embedding_revision"):
        bulk(http, name, [doc])
