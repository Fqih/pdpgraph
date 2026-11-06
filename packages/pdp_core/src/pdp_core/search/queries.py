# SPDX-License-Identifier: Apache-2.0
"""Query bodies for `legal_units` (03 §5.2, M1.6): BM25 field sets, dense k-NN, RRF fusion.

Every query is filtered to units valid at `as_of` (`valid_from <= as_of < valid_to`, a missing
`valid_to` is open). The field sets are untuned defaults; tuning is M1.10 with the eval (06).
"""

from collections.abc import Iterable
from datetime import date
from typing import Any

RRF_K = 60  # 03 §5.2
FIELDS = {
    "bm25_plain": ["text"],
    "bm25_stem": ["text.stem"],
    "multi_field": [
        "text",
        "text.stem",
        "text.shingle",
        "context_text",
        "context_text.stem",
        "penjelasan_text^0.5",
        "penjelasan_text.stem^0.5",
    ],
}


def validity_filter(as_of: date) -> list[dict[str, Any]]:
    day = as_of.isoformat()
    return [
        {"range": {"valid_from": {"lte": day}}},
        {
            "bool": {
                "should": [
                    {"bool": {"must_not": {"exists": {"field": "valid_to"}}}},
                    {"range": {"valid_to": {"gt": day}}},
                ],
                "minimum_should_match": 1,
            }
        },
    ]


def bm25_body(query: str, fields: list[str], as_of: date, *, k: int) -> dict[str, Any]:
    match = {"multi_match": {"query": query, "fields": fields, "type": "most_fields"}}
    return {
        "size": k,
        "_source": ["unit_id"],
        "query": {"bool": {"must": [match], "filter": validity_filter(as_of)}},
    }


def knn_body(vector: list[float], as_of: date, *, k: int) -> dict[str, Any]:
    knn = {"vector": vector, "k": k, "filter": {"bool": {"filter": validity_filter(as_of)}}}
    return {"size": k, "_source": ["unit_id"], "query": {"knn": {"embedding": knn}}}


def rrf(rankings: Iterable[list[str]], k: int = RRF_K) -> list[str]:
    """Reciprocal-rank fusion: score(d) = sum 1 / (k + rank); ties keep first-seen order."""
    if k <= 0:
        raise ValueError("k must be positive")
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc in enumerate(ranking, start=1):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda d: -scores[d])
