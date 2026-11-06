# SPDX-License-Identifier: Apache-2.0
"""OpenSearch REST calls for `legal_units` (M1.6) over httpx; no client library needed."""

import json
from typing import Any

import httpx

_MODEL_KEYS = ("embedding_model", "embedding_revision", "embedding_dim")


class EmbeddingMixError(Exception):
    """Vectors of another embedding model or revision would land in one index."""


def check_embedding(meta: dict[str, Any], *, model: str, revision: str, dim: int) -> None:
    wanted = {"embedding_model": model, "embedding_revision": revision, "embedding_dim": dim}
    wrong = {k: (meta.get(k), v) for k, v in wanted.items() if meta.get(k) != v}
    if wrong:
        raise EmbeddingMixError(f"index holds another embedding (index, new): {wrong}")


def _meta(http: httpx.Client, name: str) -> dict[str, Any] | None:
    r = http.get(f"/{name}/_mapping")
    if r.status_code == 404:
        return None
    r.raise_for_status()
    meta: dict[str, Any] = r.json()[name]["mappings"].get("_meta", {})
    return meta


def ensure_index(http: httpx.Client, name: str, body: dict[str, Any]) -> None:
    """Create the index, or check that the existing one has the same embedding model."""
    want = body["mappings"]["_meta"]
    meta = _meta(http, name)
    if meta is None:
        http.put(f"/{name}", json=body).raise_for_status()
        return
    check_embedding(
        meta,
        model=want["embedding_model"],
        revision=want["embedding_revision"],
        dim=want["embedding_dim"],
    )


def bulk(http: httpx.Client, name: str, docs: list[dict[str, Any]]) -> None:
    """Index documents by `node_id` (idempotent); visible to search on return."""
    meta = _meta(http, name)
    if meta is None:
        raise KeyError(name)
    for d in docs:
        check_embedding(
            meta,
            model=d["embedding_model"],
            revision=d["embedding_revision"],
            dim=len(d["embedding"]),
        )
    lines = []
    for d in docs:
        lines.append(json.dumps({"index": {"_index": name, "_id": d["node_id"]}}))
        lines.append(json.dumps(d, ensure_ascii=False, default=str))
    r = http.post(
        "/_bulk?refresh=wait_for",
        content="\n".join(lines) + "\n",
        headers={"content-type": "application/x-ndjson"},
    )
    r.raise_for_status()
    if r.json()["errors"]:
        failed = [i["index"] for i in r.json()["items"] if "error" in i["index"]][:3]
        raise RuntimeError(f"bulk indexing failed: {failed}")


def alias_targets(http: httpx.Client, alias: str) -> list[str]:
    r = http.get(f"/_alias/{alias}")
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return sorted(r.json())


def swap_alias(http: httpx.Client, alias: str, name: str) -> list[str]:
    """Point `alias` at `name` only, in one atomic `_aliases` call; returns the old targets."""
    old = alias_targets(http, alias)
    actions: list[dict[str, Any]] = [
        {"remove": {"index": i, "alias": alias}} for i in old if i != name
    ]
    actions.append({"add": {"index": name, "alias": alias}})
    http.post("/_aliases", json={"actions": actions}).raise_for_status()
    return [i for i in old if i != name]


def analyze(http: httpx.Client, index: str, field: str, text: str) -> list[str]:
    r = http.post(f"/{index}/_analyze", json={"field": field, "text": text})
    r.raise_for_status()
    return [t["token"] for t in r.json()["tokens"]]


def search_ids(http: httpx.Client, index: str, body: dict[str, Any]) -> list[str]:
    """`unit_id`s of the hits, best first."""
    r = http.post(f"/{index}/_search", json=body)
    r.raise_for_status()
    return [h["_source"]["unit_id"] for h in r.json()["hits"]["hits"]]
