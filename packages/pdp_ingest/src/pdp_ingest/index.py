# SPDX-License-Identifier: Apache-2.0
"""`index` stage (03 §5.1, M1.6, FR-PDP-07): stage artifacts -> OpenSearch `legal_units`.

One document per citable unit (04 §4): AYAT, HURUF, ANGKA, PASAL only when it has no ayat, and
every substantive Penjelasan (not "Cukup jelas.") as kind PENJELASAN with `explains` = the unit it
explains (absent for the general Penjelasan). Per document:
- `text`: the unit text;
- `context_text`: structure headings (BAB, Bagian, Paragraf) top-down, the texts of the
  ancestor units (lead-ins such as "... meliputi:"), then the unit label, joined by " / ";
- `penjelasan_text`: Penjelasan of the unit and its ancestors, "Cukup jelas." dropped (empty on
  Penjelasan documents, whose own text is `text`, and whose context adds the explained label);
- `terms`: `term_norm` of the defined terms the unit uses (`USES_TERM`); `concepts`: empty
  until concept tagging lands;
- `valid_from` = Source.effective_from, no `valid_to` (version 1, as in the graph);
- `embedding`: bge-m3 dense vector of the ancestor lead-ins + the unit text, from models-aux.

While embedding, the bge-m3 multi-vector (ColBERT) outputs are cached per unit in
`data/processed/<id>/multivectors/<model>@<revision[:12]>.jsonl` (float16). They are neither
indexed nor used: they are for the M1.10 rerank experiment.

Every run builds a new index `legal_units_v<build>` (never the live one), moves the
`legal_units` alias to it in one atomic call, keeps the previous build for rollback and deletes
older ones (`SEARCH_INDEX_RETENTION`, default 2). An index never mixes embedding models.

`python -m pdp_ingest.index --source uu27-2022` (`make index SOURCE=...`).
"""

import argparse
import base64
import json
import struct
import time
from collections import Counter
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
    check_embedding,
    embed,
    index_body,
    protected_keywords,
    publish,
)
from pdp_ingest.graph_load import VERSION, _jsonl

__all__ = ["EmbeddingMixError", "check_embedding"]

Row = dict[str, Any]
_STRUCTURES = {"BAB", "BAGIAN", "PARAGRAF"}
_INDEXED = {"AYAT", "HURUF", "ANGKA"}  # plus PASAL without ayat, substantive PENJELASAN
_NO_EXPLANATION = "Cukup jelas"
SEP = " / "


@dataclass(frozen=True)
class MultiVectors:
    node_id: str
    model: str
    revision: str
    vectors: list[list[float]]  # one per token


def _substantive(u: Row) -> bool:
    return u["kind"] == "PENJELASAN" and not u["text"].startswith(_NO_EXPLANATION)


def _citable(units: list[Row]) -> list[Row]:
    has_ayat = {u["parent_id"] for u in units if u["kind"] == "AYAT"}
    return [
        u
        for u in units
        if u["kind"] in _INDEXED
        or (u["kind"] == "PASAL" and u["unit_id"] not in has_ayat)
        or _substantive(u)
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

    def ancestors(u: Row) -> list[str]:
        """Ancestor ids, top-down; a Penjelasan's parent is the unit it explains."""
        chain: list[str] = []
        parent = u["parent_id"]
        while parent:
            chain.append(parent)
            parent = (by_id.get(parent) or structures[parent])["parent_id"]
        return chain[::-1]

    docs = []
    for u in _citable(units):
        chain = ancestors(u)
        units_up = [by_id[p] for p in chain if p in by_id]
        headings = [structures[p]["heading"] for p in chain if p in structures]
        leads = [a["text"] for a in units_up if a["text"]]
        labels = [u["label"]]
        notes: list[str] = []
        if u["kind"] == "PENJELASAN":
            if u["parent_id"]:
                labels.insert(0, by_id[u["parent_id"]]["label"])
        else:
            notes = [
                by_id[f"{p}#pj"]["text"]
                for p in [*(a["unit_id"] for a in units_up), u["unit_id"]]
                if f"{p}#pj" in by_id and _substantive(by_id[f"{p}#pj"])
            ]
        doc = {
            "node_id": f"{u['unit_id']}@{VERSION}",
            "unit_id": u["unit_id"],
            "source_id": source["source_id"],
            "kind": u["kind"],
            "label": u["label"],
            "text": u["text"],
            "context_text": SEP.join([*headings, *leads, *labels]),
            "penjelasan_text": "\n".join(notes),
            "terms": sorted(terms.get(u["unit_id"], ())),
            "concepts": [],
            "valid_from": date.fromisoformat(source["effective_from"]),
            "embedding_input": " ".join([*leads, u["text"]]),
        }
        if u["kind"] == "PENJELASAN" and u["parent_id"]:
            doc["explains"] = u["parent_id"]
        docs.append(doc)
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
    with httpx.Client(base_url=settings.opensearch_url, timeout=120) as http:
        start = time.perf_counter()
        docs_out = with_embeddings(docs, vectors, model=model, revision=revision)
        pub = publish(http, docs_out, body, retention=settings.index_retention)
        index_s = time.perf_counter() - start
        stats = http.get(f"/{pub.name}/_stats/store,docs").json()["indices"][pub.name]
    kinds = Counter(d["kind"] for d in docs)
    print(f"index {args.source}: {len(docs)} documents {dict(kinds)} into {pub.name}")
    print(f"{ALIAS} -> {pub.name} (was {pub.previous}); pruned {pub.deleted}")
    print(f"embedding ({model}@{revision[:12]}, dense + multi-vector): {embed_s:.1f} s")
    print(f"opensearch create + write + alias swap + prune: {index_s:.1f} s")
    primaries = stats["primaries"]
    print(f"docs {primaries['docs']['count']}, store {primaries['store']['size_in_bytes']} bytes")


if __name__ == "__main__":
    main()
