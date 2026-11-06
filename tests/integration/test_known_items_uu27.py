# SPDX-License-Identifier: Apache-2.0
"""Known-item queries on the UU 27/2022 index: hybrid RRF returns each owner-confirmed expected
unit in its top 10 (M1.6 DoD, FR-PDP-07). Local only.

Needs `make up`, models-aux (`make up-llm`) and `make index SOURCE=uu27-2022` (embeddings of the
git-ignored text). Unconfirmed items are skipped: the owner confirms them in
`data/review/uu27-2022/known_items.md`. Smoke check only; no tuning on these queries.
"""

from datetime import date
from pathlib import Path

import httpx
import pytest

from pdp_core.search import ALIAS, SearchSettings, alias_targets
from pdp_eval.known_items import KnownItem, first_rank, rankings, read_known_items

ROOT = Path(__file__).resolve().parents[2]
S = "uu27-2022"
ITEMS = read_known_items((ROOT / "data" / "review" / S / "known_items.md").read_text("utf-8"))
TOP_K = 10
DAY = date(2025, 1, 1)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.needs_corpus,
    pytest.mark.skipif(
        not (ROOT / "data" / "processed" / S / "units.jsonl").is_file(),
        reason=f"no stage artifacts; run `make ingest SOURCE={S}` and `make index SOURCE={S}`",
    ),
]


@pytest.mark.parametrize("item", ITEMS, ids=[i.id for i in ITEMS])
def test_hybrid_finds_the_expected_unit(item: KnownItem) -> None:
    if not item.confirmed:
        pytest.skip(f"{item.id}: not confirmed by the owner yet")
    settings = SearchSettings()
    with (
        httpx.Client(base_url=settings.opensearch_url, timeout=30) as search,
        httpx.Client(base_url=settings.models_aux_url, timeout=60) as aux,
    ):
        if not alias_targets(search, ALIAS):
            pytest.fail(f"no {ALIAS} alias; run `make index SOURCE={S}`")
        ranks = rankings(search, aux, item.query, DAY, k=TOP_K)
    assert first_rank(ranks["hybrid_rrf"], item.expected) is not None, ranks["hybrid_rrf"]
