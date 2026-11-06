# SPDX-License-Identifier: Apache-2.0
"""Text-free structure artifact of a source graph (M1.5): ids, kinds, order, edges, hashes.

The law text is not redistributed ([VERIFY], 01 §6), so CI cannot load the real graph from
`data/processed/`. `export_structure` keeps every id, kind, order, edge, edge property and
provenance field, and drops every text field; units and definitions keep the SHA-256 of their
text. `read_structure` gives a `GraphData` that `load` turns into a text-less graph: the same
nodes and edges, without `text`, `heading`, `term` or `mention_text`.

`tests/fixtures/<source_id>/structure.json` is committed; a snapshot test checks it equals the
export of a fresh `make ingest` run.
"""

import json
from dataclasses import fields
from datetime import date
from pathlib import Path
from typing import Any

from pdp_ingest.graph_load import GraphData, Row

TEXT_KEYS: dict[str, frozenset[str]] = {
    "structures": frozenset({"heading"}),
    "units": frozenset({"text", "text_norm"}),
    "definitions": frozenset({"term", "term_norm", "aliases", "text"}),
    "categories": frozenset({"label", "explanation"}),
    "references": frozenset({"mention_text"}),
}
_DATES = {
    "sources": ("enacted_on", "promulgated_on", "effective_from"),
    "units": ("valid_from", "valid_to"),
}


def export_structure(g: GraphData) -> dict[str, list[Row]]:
    """Every row of `g` without its text fields."""
    out: dict[str, list[Row]] = {}
    for f in fields(g):
        drop = TEXT_KEYS.get(f.name, frozenset())
        out[f.name] = [
            {k: v for k, v in row.items() if k not in drop} for row in getattr(g, f.name)
        ]
    return out


def _iso(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"not JSON serializable: {value!r}")


def write_structure(g: GraphData, path: Path) -> None:
    """Deterministic JSON: sorted keys, ISO dates, one trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        export_structure(g), ensure_ascii=False, indent=1, sort_keys=True, default=_iso
    )
    path.write_text(text + "\n", encoding="utf-8")


def read_structure(path: Path) -> GraphData:
    data = json.loads(path.read_text(encoding="utf-8"))
    for group, keys in _DATES.items():
        for row in data[group]:
            for k in keys:
                if k in row:
                    row[k] = date.fromisoformat(row[k])
    return GraphData(**data)
