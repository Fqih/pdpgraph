# SPDX-License-Identifier: Apache-2.0
"""`legal_units` search index (04 §4, M1.6)."""

from pdp_core.search.embed import Embedded, embed
from pdp_core.search.mapping import (
    ACTORS,
    ALIAS,
    INDEX_VERSION,
    index_body,
    index_name,
    protected_keywords,
)
from pdp_core.search.queries import FIELDS, RRF_K, bm25_body, knn_body, rrf, validity_filter
from pdp_core.search.settings import SearchSettings
from pdp_core.search.store import (
    EmbeddingMixError,
    alias_targets,
    analyze,
    bulk,
    check_embedding,
    ensure_index,
    search_ids,
    swap_alias,
)

__all__ = [
    "ACTORS",
    "ALIAS",
    "FIELDS",
    "INDEX_VERSION",
    "RRF_K",
    "Embedded",
    "EmbeddingMixError",
    "SearchSettings",
    "alias_targets",
    "analyze",
    "bm25_body",
    "bulk",
    "check_embedding",
    "embed",
    "ensure_index",
    "index_body",
    "index_name",
    "knn_body",
    "protected_keywords",
    "rrf",
    "search_ids",
    "swap_alias",
    "validity_filter",
]
