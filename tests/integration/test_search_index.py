# SPDX-License-Identifier: Apache-2.0
"""`legal_units` index in OpenSearch: mapping, protected terms, builds and alias swap,
retention, model guard, queries, and the test guard itself (M1.6, FR-PDP-07). Needs `make up`.

Every index and alias here has a per-test `itest-<hex>-` prefix; the `opensearch` fixture
refuses any write outside `itest-*`, so the dev `legal_units` alias and indexes are never
touched.
"""

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

import httpx
import pytest

from pdp_core.search import (
    ALIAS,
    FIELDS,
    EmbeddingMixError,
    IndexExistsError,
    alias_targets,
    analyze,
    bm25_body,
    builds,
    bulk,
    create_index,
    index_body,
    index_name,
    knn_body,
    next_build,
    prune,
    publish,
    search_ids,
    swap_alias,
)

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "tests" / "fixtures" / "uu27-2022" / "legal_units.index.json"
REV = "a" * 40
DAY = date(2025, 1, 1)


def _body(dim: int = 2, revision: str = REV) -> dict[str, object]:
    return index_body(["pribadi"], model="m/x", revision=revision, dim=dim)


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


def _live_state(http: httpx.Client) -> tuple[object, object]:
    r = http.get(f"/_cat/indices/{ALIAS}*", params={"format": "json", "h": "index"})
    indices = sorted(i["index"] for i in r.json()) if r.status_code == 200 else []
    return indices, alias_targets(http, ALIAS)


def test_guard_refuses_live_names(opensearch: httpx.Client, itest_prefix: str) -> None:
    before = _live_state(opensearch)
    attempts: list[Callable[[], object]] = [
        lambda: opensearch.put("/legal_units_v1", json=_body()),
        lambda: create_index(opensearch, "legal_units_v99", _body()),
        lambda: opensearch.delete("/legal_units_v1"),
        lambda: opensearch.delete("/legal_units*"),
        lambda: opensearch.delete(f"/{itest_prefix}x,legal_units_v1"),
        lambda: opensearch.put("/legal_units_v1/_mapping", json={}),
        lambda: swap_alias(opensearch, ALIAS, f"{itest_prefix}legal_units_v1"),
        lambda: opensearch.post(
            "/_aliases", json={"actions": [{"add": {"index": "legal_units_v1", "alias": "x"}}]}
        ),
        lambda: opensearch.post(
            "/_bulk",
            content=json.dumps({"index": {"_index": "legal_units_v1", "_id": "x"}}) + "\n{}\n",
            headers={"content-type": "application/x-ndjson"},
        ),
    ]
    for attempt in attempts:
        with pytest.raises(Exception, match="integration tests write only itest-"):
            attempt()
    assert _live_state(opensearch) == before


def test_session_cleanup_deletes_leftover_itest_indices(
    opensearch: httpx.Client, delete_itest: Callable[[], None]
) -> None:
    opensearch.put("/itest-leftover-0").raise_for_status()
    delete_itest()
    r = opensearch.get("/_cat/indices/itest-leftover-*", params={"format": "json"})
    assert r.json() == []


def test_mapping_is_stored_as_built(opensearch: httpx.Client, itest_prefix: str) -> None:
    body = _body(dim=4)
    name = index_name(1, prefix=itest_prefix)
    create_index(opensearch, name, body)
    stored = opensearch.get(f"/{name}/_mapping").json()[name]["mappings"]
    assert stored["_meta"] == body["mappings"]["_meta"]  # type: ignore[index]
    assert stored["dynamic"] == "strict"
    props = body["mappings"]["properties"]  # type: ignore[index]
    assert stored["properties"]["text"] == props["text"]
    assert stored["properties"]["explains"] == {"type": "keyword"}
    assert stored["properties"]["embedding"]["dimension"] == 4
    assert set(stored["properties"]) == set(props)


def test_protected_terms_stay_intact_in_text_stem(
    opensearch: httpx.Client, itest_prefix: str
) -> None:
    name = index_name(1, prefix=itest_prefix)
    create_index(opensearch, name, json.loads(SNAPSHOT.read_text(encoding="utf-8")))
    text = "Pengendali Data Pribadi dan Prosesor Data Pribadi"
    assert analyze(opensearch, name, "text.stem", text) == [
        "pengendali",
        "data",
        "pribadi",
        "dan",
        "prosesor",
        "data",
        "pribadi",
    ]
    # ordinary words still stem
    stemmed = analyze(opensearch, name, "text.stem", "kewajiban memproses permintaan")
    assert stemmed == ["wajib", "proses", "minta"]
    # the same stemmer without the marker cuts them ("prosesor" it leaves alone anyway)
    bare = opensearch.post(
        "/_analyze",
        json={
            "tokenizer": "standard",
            "filter": ["lowercase", {"type": "stemmer", "language": "indonesian"}],
            "text": "Pengendali Pribadi Prosesor",
        },
    ).json()
    assert [t["token"] for t in bare["tokens"]] == ["endali", "pribad", "prosesor"]
    assert analyze(opensearch, name, "text", "Pengendali Data Pribadi") == [
        "pengendali",
        "data",
        "pribadi",
    ]


def test_alias_swap_is_atomic(opensearch: httpx.Client, itest_prefix: str) -> None:
    v1, v2 = index_name(1, prefix=itest_prefix), index_name(2, prefix=itest_prefix)
    alias = itest_prefix + ALIAS
    create_index(opensearch, v1, _body())
    create_index(opensearch, v2, _body())
    assert swap_alias(opensearch, alias, v1) == []
    assert alias_targets(opensearch, alias) == [v1]
    assert swap_alias(opensearch, alias, v2) == [v1]
    assert alias_targets(opensearch, alias) == [v2]


def test_an_existing_index_is_never_written_again(
    opensearch: httpx.Client, itest_prefix: str
) -> None:
    name = index_name(1, prefix=itest_prefix)
    create_index(opensearch, name, _body())
    with pytest.raises(IndexExistsError):
        create_index(opensearch, name, _body())


def test_bulk_refuses_documents_of_another_model(
    opensearch: httpx.Client, itest_prefix: str
) -> None:
    name = index_name(1, prefix=itest_prefix)
    create_index(opensearch, name, _body())
    doc = _doc("a1", "x", [1.0, 0.0], "2022-10-17") | {"embedding_revision": "b" * 40}
    with pytest.raises(EmbeddingMixError, match="embedding_revision"):
        bulk(opensearch, name, [doc])


def test_builds_and_retention(opensearch: httpx.Client, itest_prefix: str) -> None:
    alias = itest_prefix + ALIAS
    assert next_build(opensearch, prefix=itest_prefix) == 1
    deleted_per_build = []
    for build in (1, 2, 3):
        name = index_name(build, prefix=itest_prefix)
        create_index(opensearch, name, _body())
        swap_alias(opensearch, alias, name)
        deleted_per_build.append(prune(opensearch, alias, keep=2, prefix=itest_prefix))
    assert deleted_per_build == [[], [], [index_name(1, prefix=itest_prefix)]]
    assert builds(opensearch, prefix=itest_prefix) == [
        index_name(2, prefix=itest_prefix),
        index_name(3, prefix=itest_prefix),
    ]
    assert next_build(opensearch, prefix=itest_prefix) == 4


def test_prune_never_deletes_the_live_index(opensearch: httpx.Client, itest_prefix: str) -> None:
    alias = itest_prefix + ALIAS
    v1, v2 = index_name(1, prefix=itest_prefix), index_name(2, prefix=itest_prefix)
    create_index(opensearch, v1, _body())
    create_index(opensearch, v2, _body())
    swap_alias(opensearch, alias, v1)  # rolled back to the older build
    assert prune(opensearch, alias, keep=1, prefix=itest_prefix) == []
    assert builds(opensearch, prefix=itest_prefix) == [v1, v2]


def test_publish_builds_a_new_index_each_time(opensearch: httpx.Client, itest_prefix: str) -> None:
    alias = itest_prefix + ALIAS
    docs = [_doc("a1", "Pengendali wajib memproses data", [1.0, 0.0], "2022-10-17")]
    names = [publish(opensearch, docs, _body(), retention=2, prefix=itest_prefix) for _ in range(3)]
    v = [index_name(b, prefix=itest_prefix) for b in (1, 2, 3)]
    assert [(p.name, p.previous, p.deleted) for p in names] == [
        (v[0], [], []),
        (v[1], [v[0]], []),
        (v[2], [v[1]], [v[0]]),
    ]
    assert alias_targets(opensearch, alias) == [v[2]]
    assert search_ids(opensearch, alias, bm25_body("proses", FIELDS["bm25_stem"], DAY, k=5)) == [
        "t/a1"
    ]


def test_bm25_knn_and_validity(opensearch: httpx.Client, itest_prefix: str) -> None:
    name = index_name(1, prefix=itest_prefix)
    create_index(opensearch, name, _body())
    bulk(
        opensearch,
        name,
        [
            _doc("a1", "Pengendali wajib memproses data", [1.0, 0.0], "2022-10-17"),
            _doc("a2", "Subjek berhak meminta salinan", [0.0, 1.0], "2022-10-17"),
            _doc("a3", "Pengendali wajib memproses ulang", [1.0, 0.1], "2030-01-01"),
        ],
    )
    stem = bm25_body("proses", FIELDS["bm25_stem"], DAY, k=5)
    assert search_ids(opensearch, name, stem) == ["t/a1"]
    assert search_ids(opensearch, name, bm25_body("proses", FIELDS["bm25_plain"], DAY, k=5)) == []
    assert search_ids(opensearch, name, knn_body([0.0, 1.0], DAY, k=2))[0] == "t/a2"
    assert "t/a3" not in search_ids(opensearch, name, knn_body([1.0, 0.1], DAY, k=3))
