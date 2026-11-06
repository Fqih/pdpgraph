# SPDX-License-Identifier: Apache-2.0
"""Known-item smoke check for the `legal_units` index (M1.6, FR-PDP-07).

`data/review/<source_id>/known_items.md` lists queries with one expected unit each, proposed by
Claude; an item counts only once the owner sets `verdict: confirmed` (a wrong expectation is
fixed in the `Expected:` line first). This is a smoke check, not an eval: the queries are never
used for tuning, and the numbers are reported as-is.

`python -m pdp_eval.known_items --source uu27-2022` prints, per query, the rank of the expected
unit in the top `k` of each mode: BM25 on `text` (no stemming), on `text.stem`, multi-field BM25,
dense k-NN, and hybrid RRF of multi-field + dense (03 §5.2).
"""

import argparse
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

from pdp_core.search import (
    ALIAS,
    FIELDS,
    SearchSettings,
    bm25_body,
    embed,
    knn_body,
    rrf,
    search_ids,
)
from pdp_ingest.review import read_reviews

VERDICTS = ("confirmed", "wrong_expected", "drop")
MODES = ("bm25_plain", "bm25_stem", "multi_field", "dense", "hybrid_rrf")
_ITEM = re.compile(r"### `([^`]+)` (.+)")
_QUERY = re.compile(r"Query: (.+)")
_EXPECTED = re.compile(r"Expected: `([^`]+)`")


@dataclass(frozen=True)
class KnownItem:
    id: str
    kind: str
    query: str
    expected: str  # unit_id
    confirmed: bool


def read_known_items(text: str) -> list[KnownItem]:
    reviews = read_reviews(text, VERDICTS)
    found: list[dict[str, str]] = []
    for line in text.splitlines():
        if m := _ITEM.match(line):
            found.append({"id": m.group(1), "kind": m.group(2)})
        elif found and (m := _QUERY.match(line)):
            found[-1]["query"] = m.group(1).strip()
        elif found and (m := _EXPECTED.match(line)):
            found[-1]["expected"] = m.group(1)
    items = []
    for f in found:
        if "query" not in f or "expected" not in f:
            raise ValueError(f"{f['id']}: needs a Query: and an Expected: line")
        review = next((r for (_, i), r in reviews.items() if i == f["id"]), None)
        confirmed = review is not None and review.verdict == "confirmed"
        items.append(KnownItem(f["id"], f["kind"], f["query"], f["expected"], confirmed))
    return items


def first_rank(ranking: list[str], expected: str) -> int | None:
    return ranking.index(expected) + 1 if expected in ranking else None


def rankings(
    search: httpx.Client, aux: httpx.Client, query: str, as_of: date, *, k: int, index: str = ALIAS
) -> dict[str, list[str]]:
    """Top-k unit ids per mode."""
    out = {
        mode: search_ids(search, index, bm25_body(query, FIELDS[mode], as_of, k=k))
        for mode in ("bm25_plain", "bm25_stem", "multi_field")
    }
    (vector,) = embed(aux, [query], "query").vectors
    out["dense"] = search_ids(search, index, knn_body(vector, as_of, k=k))
    out["hybrid_rrf"] = rrf([out["multi_field"], out["dense"]])[:k]
    return out


def main() -> None:
    parser = argparse.ArgumentParser(prog="pdp_eval.known_items")
    parser.add_argument("--source", required=True)
    parser.add_argument("--review-dir", type=Path, default=Path("data/review"))
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    path = args.review_dir / args.source / "known_items.md"
    items = read_known_items(path.read_text(encoding="utf-8"))
    settings = SearchSettings()
    print(f"rank of the expected unit in the top {args.k} ('-' = not in it); smoke only")
    print("| item | confirmed | " + " | ".join(MODES) + " |")
    print("|---|---|" + "---|" * len(MODES))
    hits = dict.fromkeys(MODES, 0)
    with (
        httpx.Client(base_url=settings.opensearch_url, timeout=30) as search,
        httpx.Client(base_url=settings.models_aux_url, timeout=60) as aux,
    ):
        for item in items:
            ranks = rankings(search, aux, item.query, args.as_of, k=args.k)
            row = [first_rank(ranks[m], item.expected) for m in MODES]
            for mode, rank in zip(MODES, row, strict=True):
                hits[mode] += rank is not None
            cells = " | ".join("-" if r is None else str(r) for r in row)
            print(f"| {item.id} | {'yes' if item.confirmed else 'no'} | {cells} |")
    print("| found | | " + " | ".join(f"{hits[m]}/{len(items)}" for m in MODES) + " |")


if __name__ == "__main__":
    main()
