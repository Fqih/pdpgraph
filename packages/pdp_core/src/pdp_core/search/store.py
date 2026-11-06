# SPDX-License-Identifier: Apache-2.0
"""OpenSearch REST calls for `legal_units` (M1.6) over httpx; no client library needed."""

import json
from dataclasses import dataclass
from typing import Any

import httpx

from pdp_core.search.mapping import ALIAS, build_number, index_name

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


class IndexExistsError(Exception):
    """A build would write into an index that already exists."""


def create_index(http: httpx.Client, name: str, body: dict[str, Any]) -> None:
    """Create a new index; an existing one is never written again (04 §4)."""
    if _meta(http, name) is not None:
        raise IndexExistsError(f"{name} exists; a build always creates a new index")
    http.put(f"/{name}", json=body).raise_for_status()


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


def builds(http: httpx.Client, *, prefix: str = "") -> list[str]:
    """Existing `legal_units_v<build>` indexes, oldest build first."""
    r = http.get(f"/_cat/indices/{prefix}{ALIAS}_v*", params={"format": "json", "h": "index"})
    if r.status_code == 404:
        return []
    r.raise_for_status()
    numbered = [(build_number(i["index"], prefix=prefix), i["index"]) for i in r.json()]
    return [name for n, name in sorted((n, name) for n, name in numbered if n is not None)]


def next_build(http: httpx.Client, *, prefix: str = "") -> int:
    existing = [build_number(n, prefix=prefix) or 0 for n in builds(http, prefix=prefix)]
    return max(existing, default=0) + 1


def prune(http: httpx.Client, alias: str, *, keep: int, prefix: str = "") -> list[str]:
    """Delete all but the newest `keep` builds; never an index the alias points at."""
    if keep < 1:
        raise ValueError("keep must be at least 1")
    live = set(alias_targets(http, alias))
    doomed = [n for n in builds(http, prefix=prefix)[:-keep] if n not in live]
    for name in doomed:
        http.delete(f"/{name}").raise_for_status()
    return doomed


@dataclass(frozen=True)
class Published:
    name: str
    previous: list[str]  # alias targets before the swap (kept for rollback)
    deleted: list[str]  # builds pruned beyond the retention


def publish(
    http: httpx.Client,
    docs: list[dict[str, Any]],
    body: dict[str, Any],
    *,
    retention: int,
    prefix: str = "",
) -> Published:
    """New build index, documents, atomic alias swap, then prune to `retention` builds."""
    alias = prefix + ALIAS
    name = index_name(next_build(http, prefix=prefix), prefix=prefix)
    if name in alias_targets(http, alias):
        raise IndexExistsError(f"{name} is live; never rebuild into the live index")
    create_index(http, name, body)
    bulk(http, name, docs)
    previous = swap_alias(http, alias, name)
    return Published(name, previous, prune(http, alias, keep=retention, prefix=prefix))


def analyze(http: httpx.Client, index: str, field: str, text: str) -> list[str]:
    r = http.post(f"/{index}/_analyze", json={"field": field, "text": text})
    r.raise_for_status()
    return [t["token"] for t in r.json()["tokens"]]


def search_ids(http: httpx.Client, index: str, body: dict[str, Any]) -> list[str]:
    """`unit_id`s of the hits, best first."""
    r = http.post(f"/{index}/_search", json=body)
    r.raise_for_status()
    return [h["_source"]["unit_id"] for h in r.json()["hits"]["hits"]]
