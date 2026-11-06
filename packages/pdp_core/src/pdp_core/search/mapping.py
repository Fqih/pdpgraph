# SPDX-License-Identifier: Apache-2.0
"""`legal_units` index body (04 §4, M1.6): fields, analyzers, protected terms, model metadata.

Analyzers (no stop words; BM25 idf handles them):
- `legal_plain` (`text`): standard tokenizer + lowercase, no stemming;
- `legal_stem` (`text.stem`): + `keyword_marker` with the protected terms, then the Indonesian
  stemmer, so "pengendali", "pribadi", "prosesor" stay whole while other words stem;
- `legal_shingle` (`text.shingle`): lowercase 2- and 3-word shingles, no unigrams.

The protected terms are the lowercase words of the source's defined terms and aliases
(`terms.json`, M1.4) plus the Actor vocabulary (04 §3.1). `_meta` records the embedding model,
revision and dim; one index never mixes models (`store.bulk`). Every build is a new index
(`legal_units_v<build>`); `store.publish` swaps the alias and prunes old builds.
"""

from collections.abc import Iterable
from typing import Any

MAPPING_VERSION = 1  # bump when the body changes (recorded in `_meta`)
ALIAS = "legal_units"
ACTORS = ("PENGENDALI", "PROSESOR", "SUBJEK_DATA", "LEMBAGA", "DPO", "PIHAK_KETIGA")
_TEXT = {"type": "text", "analyzer": "legal_plain"}


def index_name(build: int, *, prefix: str = "") -> str:
    """`legal_units_v<build>`: every index build gets a new name (04 §4)."""
    return f"{prefix}{ALIAS}_v{build}"


def build_number(name: str, *, prefix: str = "") -> int | None:
    head = f"{prefix}{ALIAS}_v"
    tail = name.removeprefix(head)
    return int(tail) if name.startswith(head) and tail.isdigit() else None


def protected_keywords(terms: Iterable[str]) -> list[str]:
    words = {w.lower() for t in terms for w in t.split()}
    words |= {w.lower() for a in ACTORS for w in a.split("_")}
    return sorted(words)


def _stemmed_text() -> dict[str, Any]:
    return _TEXT | {"fields": {"stem": {"type": "text", "analyzer": "legal_stem"}}}


def index_body(keywords: list[str], *, model: str, revision: str, dim: int) -> dict[str, Any]:
    keyword: dict[str, Any] = {"type": "keyword"}
    return {
        "settings": {
            "index": {"number_of_shards": 1, "number_of_replicas": 0, "knn": True},
            "analysis": {
                "filter": {
                    "protected_terms": {
                        "type": "keyword_marker",
                        "keywords": keywords,
                        "ignore_case": True,
                    },
                    "indonesian_stemmer": {"type": "stemmer", "language": "indonesian"},
                    "shingle_2_3": {
                        "type": "shingle",
                        "min_shingle_size": 2,
                        "max_shingle_size": 3,
                        "output_unigrams": False,
                    },
                },
                "analyzer": {
                    "legal_plain": {"tokenizer": "standard", "filter": ["lowercase"]},
                    "legal_stem": {
                        "tokenizer": "standard",
                        "filter": ["lowercase", "protected_terms", "indonesian_stemmer"],
                    },
                    "legal_shingle": {
                        "tokenizer": "standard",
                        "filter": ["lowercase", "shingle_2_3"],
                    },
                },
            },
        },
        "mappings": {
            "dynamic": "strict",
            "_meta": {
                "embedding_model": model,
                "embedding_revision": revision,
                "embedding_dim": dim,
                "mapping_version": MAPPING_VERSION,
            },
            "properties": {
                "node_id": keyword,
                "unit_id": keyword,
                "source_id": keyword,
                "kind": keyword,
                "label": keyword,
                "explains": keyword,
                "text": _TEXT
                | {
                    "fields": {
                        "stem": {"type": "text", "analyzer": "legal_stem"},
                        "shingle": {"type": "text", "analyzer": "legal_shingle"},
                    }
                },
                "context_text": _stemmed_text(),
                "penjelasan_text": _stemmed_text(),
                "terms": keyword,
                "concepts": keyword,
                "valid_from": {"type": "date"},
                "valid_to": {"type": "date"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": dim,
                    "method": {"name": "hnsw", "space_type": "cosinesimil", "engine": "lucene"},
                },
                "embedding_model": keyword,
                "embedding_revision": keyword,
            },
        },
    }
