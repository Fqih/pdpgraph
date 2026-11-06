# SPDX-License-Identifier: Apache-2.0
"""`load_graph` stage (03 §5.1, M1.5, FR-PDP-06): stage artifacts -> Neo4j.

Reads only the artifacts in `data/processed/<source_id>/` (nothing is re-parsed) plus the owner's
category verdicts in `data/review/<source_id>/definitions.md`. Every node is MERGEd on its id and
its properties are replaced (`SET n = row`), every edge is MERGEd on its endpoints (REFERENCES
also on the mention start), in batched write transactions. A re-run with the same artifacts
gives the same nodes, edges and properties.

Version 1 of every legal unit is valid from the source's `effective_from`, with no `valid_to`
(Neo4j stores no nulls; a missing `valid_to` is open). Edges (04 §3.2): PART_OF {order},
IN_SOURCE, EXPLAINED_BY, REFERENCES {mention_text, resolution, start, end} per internal target,
DEFINES, USES_TERM {count, informal_count, nested_in_informal, ambiguous_case} for defined uses
only, SUBCATEGORY_OF. Delegations, SELF and external mentions, and informal-only uses get no edge.

`python -m pdp_ingest.graph_load --source uu27-2022` (`make load-graph SOURCE=...`).
"""

import argparse
import hashlib
import json
import time
import unicodedata
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, LiteralString

from neo4j import Driver, ManagedTransaction

from pdp_core.graph import CONSTRAINTS, connect
from pdp_ingest.defs_review import CATEGORY_SECTION, read_defs_reviews

Row = dict[str, Any]
ARTIFACTS = (
    "source.json",
    "structures.jsonl",
    "units.jsonl",
    "refs.jsonl",
    "defs.jsonl",
    "term_uses.jsonl",
    "data_categories.jsonl",
)
VERSION = 1  # every unit is version 1 until amendments land (M4.4)


class ArtifactError(Exception):
    """A stage artifact is missing or inconsistent."""


def text_norm(text: str) -> str:
    """NFC, lowercase, whitespace collapsed (the `text_norm` property, 04 §3.1)."""
    return " ".join(unicodedata.normalize("NFC", text).lower().split())


def _node(unit_id: str) -> str:
    return f"{unit_id}@{VERSION}"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _jsonl(path: Path) -> list[Row]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@dataclass
class GraphData:
    sources: list[Row] = field(default_factory=list)
    structures: list[Row] = field(default_factory=list)
    units: list[Row] = field(default_factory=list)
    definitions: list[Row] = field(default_factory=list)
    categories: list[Row] = field(default_factory=list)
    part_of: list[Row] = field(default_factory=list)
    explained_by: list[Row] = field(default_factory=list)
    references: list[Row] = field(default_factory=list)
    defines: list[Row] = field(default_factory=list)
    uses_term: list[Row] = field(default_factory=list)
    subcategory_of: list[Row] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        """Expected graph counts for this source (consistency check, M1.5)."""
        kinds = Counter(s["kind"] for s in self.structures)
        nodes = len(self.structures) + len(self.units) + len(self.definitions)
        return {
            "Source": len(self.sources),
            "Structure": len(self.structures),
            "BAB": kinds["BAB"],
            "BAGIAN": kinds["BAGIAN"],
            "PARAGRAF": kinds["PARAGRAF"],
            "LegalUnit": len(self.units),
            "Definition": len(self.definitions),
            "DataCategory": len(self.categories),
            "PART_OF": len(self.part_of),
            "IN_SOURCE": nodes + len(self.categories),
            "EXPLAINED_BY": len(self.explained_by),
            "REFERENCES": len(self.references),
            "DEFINES": len(self.defines),
            "USES_TERM": len(self.uses_term),
            "SUBCATEGORY_OF": len(self.subcategory_of),
        }


def read_graph(processed: Path, review: Path) -> GraphData:
    """Graph rows for one source from its artifacts and review list."""
    missing = [name for name in ARTIFACTS if not (processed / name).is_file()]
    if missing:
        raise ArtifactError(f"{processed}: missing {', '.join(missing)}; run `make ingest` first")
    source = json.loads((processed / "source.json").read_text(encoding="utf-8"))
    sid = source["source_id"]
    for key in ("enacted_on", "promulgated_on", "effective_from"):
        source[key] = date.fromisoformat(source[key])
    g = GraphData(sources=[source])
    structures = _jsonl(processed / "structures.jsonl")
    units = _jsonl(processed / "units.jsonl")
    g.structures = [
        {
            "node_id": _node(s["unit_id"]),
            "unit_id": s["unit_id"],
            "kind": s["kind"],
            "number": s["number"],
            "heading": s["heading"],
            "order": s["order"],
        }
        for s in structures
    ]
    g.units = [
        {
            "node_id": _node(u["unit_id"]),
            "unit_id": u["unit_id"],
            "kind": u["kind"],
            "label": u["label"],
            "text": u["text"],
            "text_norm": text_norm(u["text"]),
            "text_sha256": _sha256(u["text"]),
            "order": u["order"],
            "version": VERSION,
            "valid_from": source["effective_from"],
        }
        for u in units
    ]
    g.part_of = [
        {"child": _node(s["unit_id"]), "parent": _node(s["parent_id"]), "order": s["order"]}
        for s in structures
        if s["parent_id"]
    ] + [
        {"child": _node(u["unit_id"]), "parent": _node(u["parent_id"]), "order": u["order"]}
        for u in units
        if u["kind"] != "PENJELASAN" and u["parent_id"]
    ]
    g.explained_by = [
        {"unit": _node(u["parent_id"]), "pj": _node(u["unit_id"])}
        for u in units
        if u["kind"] == "PENJELASAN" and u["parent_id"]
    ]
    g.references = [
        {
            "from": _node(m["unit_id"]),
            "to": _node(t),
            "mention_text": m["text"],
            "resolution": m["resolution"],
            "start": m["start"],
            "end": m["end"],
        }
        for m in _jsonl(processed / "refs.jsonl")
        if m["kind"] == "REFERENCE"
        for t in m["targets"]
    ]
    for d in _jsonl(processed / "defs.jsonl"):
        g.definitions.append(
            {
                "node_id": _node(d["node_id"]),
                "term": d["term"],
                "term_norm": d["term_norm"],
                "aliases": d["aliases"],
                "text": d["text"],
                "text_sha256": _sha256(d["text"]),
            }
        )
        g.defines.append({"unit": _node(d["unit_id"]), "definition": _node(d["node_id"])})
    uses = _jsonl(processed / "term_uses.jsonl")
    informal = {(u["unit_id"], u["node_id"]): u["count"] for u in uses if u["kind"] == "informal"}
    g.uses_term = [
        {
            "unit": _node(u["unit_id"]),
            "definition": _node(u["node_id"]),
            "count": u["count"],
            "informal_count": informal.get((u["unit_id"], u["node_id"]), 0),
            "nested_in_informal": u["nested_in_informal"],
            "ambiguous_case": u["ambiguous_case"],
        }
        for u in uses
        if u["kind"] == "defined"
    ]
    reviews = _category_verdicts(review / "definitions.md")
    for c in _jsonl(processed / "data_categories.jsonl"):
        status = "confirmed" if reviews.get(c["unit_id"]) == "confirmed" else "proposed"
        row = {k: c[k] for k in ("code", "label", "unit_id", "open", "explanation")}
        g.categories.append(row | {"status": status, "source_id": sid})
        if c["parent_code"]:
            g.subcategory_of.append(
                {"source_id": sid, "code": c["code"], "parent": c["parent_code"]}
            )
    return g


def _category_verdicts(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    reviews = read_defs_reviews(path.read_text(encoding="utf-8"))
    return {
        unit: r.verdict for (section, unit), r in reviews.items() if section == CATEGORY_SECTION
    }


def _label(node_id: str) -> str:
    return "Structure" if "/bab" in node_id else "LegalUnit"


_NODES: dict[str, LiteralString] = {
    "Structure": "UNWIND $rows AS r MERGE (n:Structure {node_id: r.node_id}) SET n = r",
    "LegalUnit": "UNWIND $rows AS r MERGE (n:LegalUnit {node_id: r.node_id}) SET n = r",
    "Definition": "UNWIND $rows AS r MERGE (n:Definition {node_id: r.node_id}) SET n = r",
    "DataCategory": (
        "UNWIND $rows AS r MERGE (n:DataCategory {source_id: r.source_id, code: r.code}) SET n = r"
    ),
}
_IN_SOURCE: dict[str, LiteralString] = {
    label: (
        f"UNWIND $rows AS r MATCH (n:{label} {{{key}: r.{key}}}) "
        "MATCH (s:Source {source_id: $source_id}) MERGE (n)-[:IN_SOURCE]->(s)"
    )
    for label, key in (
        ("Structure", "node_id"),
        ("LegalUnit", "node_id"),
        ("Definition", "node_id"),
    )
} | {
    "DataCategory": (
        "UNWIND $rows AS r MATCH (n:DataCategory {source_id: $source_id, code: r.code}) "
        "MATCH (s:Source {source_id: $source_id}) MERGE (n)-[:IN_SOURCE]->(s)"
    )
}
_PART_OF: LiteralString = (
    "UNWIND $rows AS r MATCH (c:{child} {{node_id: r.child}}) "
    "MATCH (p:{parent} {{node_id: r.parent}}) MERGE (c)-[e:PART_OF]->(p) SET e.order = r.order"
)
_EDGES: dict[str, LiteralString] = {
    "explained_by": (
        "UNWIND $rows AS r MATCH (u:LegalUnit {node_id: r.unit}) "
        "MATCH (pj:LegalUnit {node_id: r.pj}) MERGE (u)-[:EXPLAINED_BY]->(pj)"
    ),
    "references": (
        "UNWIND $rows AS r MATCH (a:LegalUnit {node_id: r.from}) "
        "MATCH (b:LegalUnit {node_id: r.to}) MERGE (a)-[e:REFERENCES {start: r.start}]->(b) "
        "SET e.end = r.end, e.mention_text = r.mention_text, e.resolution = r.resolution"
    ),
    "defines": (
        "UNWIND $rows AS r MATCH (u:LegalUnit {node_id: r.unit}) "
        "MATCH (d:Definition {node_id: r.definition}) MERGE (u)-[:DEFINES]->(d)"
    ),
    "uses_term": (
        "UNWIND $rows AS r MATCH (u:LegalUnit {node_id: r.unit}) "
        "MATCH (d:Definition {node_id: r.definition}) MERGE (u)-[e:USES_TERM]->(d) "
        "SET e.count = r.count, e.informal_count = r.informal_count, "
        "e.nested_in_informal = r.nested_in_informal, e.ambiguous_case = r.ambiguous_case"
    ),
    "subcategory_of": (
        "UNWIND $rows AS r MATCH (c:DataCategory {source_id: r.source_id, code: r.code}) "
        "MATCH (p:DataCategory {source_id: r.source_id, code: r.parent}) "
        "MERGE (c)-[:SUBCATEGORY_OF]->(p)"
    ),
}


def _chunks(rows: list[Row], size: int) -> Iterator[list[Row]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _write(driver: Driver, query: LiteralString, rows: list[Row], size: int, **params: Any) -> None:
    def work(tx: ManagedTransaction, chunk: list[Row]) -> None:
        tx.run(query, rows=chunk, **params).consume()

    with driver.session() as session:
        for chunk in _chunks(rows, size):
            session.execute_write(work, chunk)


def ensure_schema(driver: Driver) -> None:
    """Constraints and indexes of 04 §3.3 (idempotent)."""
    for statement in CONSTRAINTS:
        driver.execute_query(statement)


def load(driver: Driver, g: GraphData, batch_size: int = 500) -> None:
    ensure_schema(driver)
    (source,) = g.sources
    sid = source["source_id"]
    _write(
        driver,
        "UNWIND $rows AS r MERGE (n:Source {source_id: r.source_id}) SET n = r",
        g.sources,
        1,
    )
    nodes = {
        "Structure": g.structures,
        "LegalUnit": g.units,
        "Definition": g.definitions,
        "DataCategory": g.categories,
    }
    for label, rows in nodes.items():
        _write(driver, _NODES[label], rows, batch_size)
        _write(driver, _IN_SOURCE[label], rows, batch_size, source_id=sid)
    groups: dict[tuple[str, str], list[Row]] = {}
    for r in g.part_of:
        groups.setdefault((_label(r["child"]), _label(r["parent"])), []).append(r)
    for (child, parent), rows in sorted(groups.items()):
        _write(driver, _PART_OF.format(child=child, parent=parent), rows, batch_size)
    for name, query in _EDGES.items():
        _write(driver, query, getattr(g, name), batch_size)


_COUNTS: LiteralString = """
MATCH (s:Source {source_id: $source_id})
RETURN
  COUNT { (s) } AS Source,
  COUNT { (n:Structure)-[:IN_SOURCE]->(s) } AS Structure,
  COUNT { (n:Structure {kind: 'BAB'})-[:IN_SOURCE]->(s) } AS BAB,
  COUNT { (n:Structure {kind: 'BAGIAN'})-[:IN_SOURCE]->(s) } AS BAGIAN,
  COUNT { (n:Structure {kind: 'PARAGRAF'})-[:IN_SOURCE]->(s) } AS PARAGRAF,
  COUNT { (n:LegalUnit)-[:IN_SOURCE]->(s) } AS LegalUnit,
  COUNT { (n:Definition)-[:IN_SOURCE]->(s) } AS Definition,
  COUNT { (n:DataCategory)-[:IN_SOURCE]->(s) } AS DataCategory,
  COUNT { (n)-[:PART_OF]->()-[:IN_SOURCE]->(s) WHERE (n)-[:IN_SOURCE]->(s) } AS PART_OF,
  COUNT { ()-[:IN_SOURCE]->(s) } AS IN_SOURCE,
  COUNT { (n)-[:EXPLAINED_BY]->()-[:IN_SOURCE]->(s) WHERE (n)-[:IN_SOURCE]->(s) } AS EXPLAINED_BY,
  COUNT { (n)-[:REFERENCES]->()-[:IN_SOURCE]->(s) WHERE (n)-[:IN_SOURCE]->(s) } AS REFERENCES,
  COUNT { (n)-[:DEFINES]->()-[:IN_SOURCE]->(s) WHERE (n)-[:IN_SOURCE]->(s) } AS DEFINES,
  COUNT { (n)-[:USES_TERM]->()-[:IN_SOURCE]->(s) WHERE (n)-[:IN_SOURCE]->(s) } AS USES_TERM,
  COUNT { (n)-[:SUBCATEGORY_OF]->()-[:IN_SOURCE]->(s) WHERE (n)-[:IN_SOURCE]->(s) }
    AS SUBCATEGORY_OF
"""


def graph_counts(driver: Driver, source_id: str) -> dict[str, int]:
    """The same counts as `GraphData.counts`, measured in the graph."""
    records, _, _ = driver.execute_query(_COUNTS, source_id=source_id)
    return dict(records[0].data()) if records else {}


def main() -> None:
    parser = argparse.ArgumentParser(prog="pdp_ingest.graph_load")
    parser.add_argument("--source", required=True)
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--review-dir", type=Path, default=Path("data/review"))
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument(
        "--export-structure",
        type=Path,
        metavar="PATH",
        help="write the text-free structure, no load",
    )
    parser.add_argument(
        "--from-structure", type=Path, metavar="PATH", help="load a text-less graph from PATH"
    )
    args = parser.parse_args()
    from pdp_ingest.graph_structure import read_structure, write_structure

    if args.from_structure:
        g = read_structure(args.from_structure)
    else:
        g = read_graph(args.processed_dir / args.source, args.review_dir / args.source)
    if args.export_structure:
        write_structure(g, args.export_structure)
        print(f"structure {args.source}: {args.export_structure}")
        return
    expected = g.counts()
    with connect() as driver:
        start = time.perf_counter()
        load(driver, g, args.batch_size)
        elapsed = time.perf_counter() - start
        actual = graph_counts(driver, args.source)
    wrong = {k: (v, actual.get(k)) for k, v in expected.items() if actual.get(k) != v}
    print(f"load_graph {args.source}: {elapsed:.2f} s")
    print(", ".join(f"{k} {v}" for k, v in actual.items()))
    if wrong:
        raise SystemExit(f"count mismatch (expected, graph): {wrong}")


if __name__ == "__main__":
    main()
