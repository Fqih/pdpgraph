# SPDX-License-Identifier: Apache-2.0
"""`index` stage (03 §5.1, M1.6, FR-PDP-07): stage artifacts -> OpenSearch `legal_units`.

One document per citable unit (04 §4): AYAT, HURUF, ANGKA, and PASAL only when it has no ayat;
never Penjelasan. Per document:
- `text`: the unit text;
- `context_text`: structure headings (BAB, Bagian, Paragraf) top-down, the texts of the
  ancestor units (lead-ins such as "... meliputi:"), then the unit label, joined by " / ";
- `penjelasan_text`: Penjelasan of the unit and its ancestors, "Cukup jelas." dropped;
- `terms`: `term_norm` of the defined terms the unit uses (`USES_TERM`); `concepts`: empty
  until concept tagging lands;
- `valid_from` = Source.effective_from, no `valid_to` (version 1, as in the graph);
- `embedding`: bge-m3 dense vector of the ancestor lead-ins + the unit text, from models-aux.

While embedding, the bge-m3 multi-vector (ColBERT) outputs are cached per unit in
`data/processed/<id>/multivectors/<model>@<revision[:12]>.jsonl` (float16). They are neither
indexed nor used: they are for the M1.10 rerank experiment.

The index is `legal_units_v<INDEX_VERSION>`; after indexing, the `legal_units` alias moves to it
in one atomic call. An index never mixes embedding models or revisions.

`python -m pdp_ingest.index --source uu27-2022` (`make index SOURCE=...`).
"""

import argparse
import base64
import json
import struct
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from pdp_core.search import (
    ALIAS,
    EmbeddingMixError,
    SearchSettings,
    bulk,
    check_embedding,
    embed,
    ensure_index,
    index_body,
    index_name,
    protected_keywords,
    swap_alias,
)
from pdp_ingest.graph_load import VERSION, _jsonl

__all__ = ["EmbeddingMixError", "check_embedding"]

Row = dict[str, Any]
_STRUCTURES = {"BAB", "BAGIAN", "PARAGRAF"}
_INDEXED = {"AYAT", "HURUF", "ANGKA"}
_NO_EXPLANATION = "Cukup jelas"
SEP = " / "


@dataclass(frozen=True)
class MultiVectors:
    node_id: str
    model: str
    revision: str
    vectors: list[list[float]]  # one per token


def _citable(units: list[Row]) -> list[Row]:
    has_ayat = {u["parent_id"] for u in units if u["kind"] == "AYAT"}
    return [
        u
        for u in units
        if u["kind"] in _INDEXED or (u["kind"] == "PASAL" and u["unit_id"] not in has_ayat)
    ]


def build_documents(processed: Path) -> list[Row]:
    """Index documents without embeddings, in document order; `embedding_input` is the text to
    embed (dropped by `with_embeddings`)."""
    source = json.loads((processed / "source.json").read_text(encoding="utf-8"))
    structures = {s["unit_id"]: s for s in _jsonl(processed / "structures.jsonl")}
    units = _jsonl(processed / "units.jsonl")
    by_id = {u["unit_id"]: u for u in units}
    defs = {d["node_id"]: d["term_norm"] for d in _jsonl(processed / "defs.jsonl")}
    terms: dict[str, set[str]] = {}
    for t in _jsonl(processed / "term_uses.jsonl"):
        if t["kind"] == "defined":
            terms.setdefault(t["unit_id"], set()).add(defs[t["node_id"]])

    docs = []
    for u in _citable(units):
        chain: list[str] = []  # ancestors, nearest first
        parent = u["parent_id"]
        while parent:
            chain.append(parent)
            parent = (by_id.get(parent) or structures[parent])["parent_id"]
        chain.reverse()
        headings = [structures[p]["heading"] for p in chain if p in structures]
        leads = [by_id[p]["text"] for p in chain if p in by_id and by_id[p]["text"]]
        notes = [
            by_id[f"{p}#pj"]["text"]
            for p in [*[c for c in chain if c in by_id], u["unit_id"]]
            if f"{p}#pj" in by_id and not by_id[f"{p}#pj"]["text"].startswith(_NO_EXPLANATION)
        ]
        docs.append(
            {
                "node_id": f"{u['unit_id']}@{VERSION}",
                "unit_id": u["unit_id"],
                "source_id": source["source_id"],
                "kind": u["kind"],
                "label": u["label"],
                "text": u["text"],
                "context_text": SEP.join([*headings, *leads, u["label"]]),
                "penjelasan_text": "\n".join(notes),
                "terms": sorted(terms.get(u["unit_id"], ())),
                "concepts": [],
                "valid_from": date.fromisoformat(source["effective_from"]),
                "embedding_input": " ".join([*leads, u["text"]]),
            }
        )
    return docs


def with_embeddings(
    docs: list[Row], vectors: list[list[float]], *, model: str, revision: str
) -> list[Row]:
    """New documents with `embedding`, `embedding_model`, `embedding_revision`."""
    return [
        {k: v for k, v in d.items() if k != "embedding_input"}
        | {"embedding": vec, "embedding_model": model, "embedding_revision": revision}
        for d, vec in zip(docs, vectors, strict=True)
    ]


def multivector_path(processed: Path, model: str, revision: str) -> Path:
    return processed / "multivectors" / f"{model.replace('/', '--')}@{revision[:12]}.jsonl"


def _f16(vectors: list[list[float]]) -> str:
    flat = [x for v in vectors for x in v]
    return base64.b64encode(struct.pack(f"<{len(flat)}e", *flat)).decode("ascii")


def _unf16(data: str, tokens: int, dim: int) -> list[list[float]]:
    flat = struct.unpack(f"<{tokens * dim}e", base64.b64decode(data))
    return [list(flat[i * dim : (i + 1) * dim]) for i in range(tokens)]


def read_multivectors(path: Path) -> dict[str, MultiVectors]:
    out = {}
    for row in _jsonl(path):
        vectors = _unf16(row["data"], row["tokens"], row["dim"])
        out[row["node_id"]] = MultiVectors(row["node_id"], row["model"], row["revision"], vectors)
    return out


def write_multivectors(path: Path, rows: list[MultiVectors]) -> None:
    """Replace the cache file; every row must carry the revision the file name is keyed by."""
    for r in rows:
        if multivector_path(path.parent.parent, r.model, r.revision) != path:
            raise EmbeddingMixError(
                f"{r.node_id}: model {r.model} revision {r.revision} does not belong in {path.name}"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {
                "node_id": r.node_id,
                "model": r.model,
                "revision": r.revision,
                "dtype": "float16",
                "tokens": len(r.vectors),
                "dim": len(r.vectors[0]) if r.vectors else 0,
                "data": _f16(r.vectors),
            }
        )
        for r in rows
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _batches(rows: list[Row], size: int) -> Iterator[list[Row]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def main() -> None:
    parser = argparse.ArgumentParser(prog="pdp_ingest.index")
    parser.add_argument("--source", required=True)
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    processed = args.processed_dir / args.source
    keywords = protected_keywords(json.loads((processed / "terms.json").read_text("utf-8")))
    settings = SearchSettings()
    docs = build_documents(processed)
    with httpx.Client(base_url=settings.models_aux_url, timeout=600) as aux:
        start = time.perf_counter()
        vectors: list[list[float]] = []
        multi: list[list[list[float]]] = []
        model = revision = ""
        dim = 0
        for batch in _batches(docs, args.batch_size):
            out = embed(aux, [d["embedding_input"] for d in batch], "passage", multi_vector=True)
            if model and (out.model, out.revision) != (model, revision):
                raise EmbeddingMixError(
                    f"models-aux changed model mid-run: {out.model}@{out.revision}"
                )
            model, revision, dim = out.model, out.revision, out.dim
            vectors += out.vectors
            multi += out.multi_vectors or []
        embed_s = time.perf_counter() - start
    body = index_body(keywords, model=model, revision=revision, dim=dim)
    write_multivectors(
        multivector_path(processed, model, revision),
        [MultiVectors(d["node_id"], model, revision, m) for d, m in zip(docs, multi, strict=True)],
    )
    name = index_name()
    with httpx.Client(base_url=settings.opensearch_url, timeout=120) as http:
        start = time.perf_counter()
        ensure_index(http, name, body)
        bulk(http, name, with_embeddings(docs, vectors, model=model, revision=revision))
        old = swap_alias(http, ALIAS, name)
        index_s = time.perf_counter() - start
        stats = http.get(f"/{name}/_stats/store,docs").json()["indices"][name]["primaries"]
    print(f"index {args.source}: {len(docs)} documents into {name} ({ALIAS} <- {name}, was {old})")
    print(f"embedding ({model}@{revision[:12]}, dense + multi-vector): {embed_s:.1f} s")
    print(f"opensearch write + alias swap: {index_s:.1f} s")
    print(f"docs {stats['docs']['count']}, store {stats['store']['size_in_bytes']} bytes")


if __name__ == "__main__":
    main()
