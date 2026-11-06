# SPDX-License-Identifier: Apache-2.0
"""Known-item review file and smoke ranks (M1.6). No services needed."""

from pathlib import Path

import pytest

from pdp_eval.known_items import KnownItem, first_rank, read_known_items
from pdp_ingest.review import ReviewError

ROOT = Path(__file__).resolve().parents[3]
TEXT = """# Known items

## 1. Queries

### `ki01` exact reference

Query: Pasal 46 ayat (1)
Expected: `uu27-2022/p46/a1`

Review: reviewed_by: faqih | verdict: confirmed

### `ki02` English paraphrase

Query: transferring personal data abroad
Expected: `uu27-2022/p56/a1`

Review: reviewed_by: - | verdict: -
"""


def test_reads_items_and_verdicts() -> None:
    a, b = read_known_items(TEXT)
    assert a == KnownItem("ki01", "exact reference", "Pasal 46 ayat (1)", "uu27-2022/p46/a1", True)
    assert b.confirmed is False
    assert b.query == "transferring personal data abroad"


def test_unknown_verdict_is_an_error() -> None:
    with pytest.raises(ReviewError, match="verdict"):
        read_known_items(TEXT.replace("verdict: confirmed", "verdict: maybe"))


def test_item_without_expected_is_an_error() -> None:
    with pytest.raises(ValueError, match="ki01"):
        read_known_items(TEXT.replace("Expected: `uu27-2022/p46/a1`\n", "", 1))


def test_first_rank() -> None:
    assert first_rank(["a", "b", "c"], "b") == 2
    assert first_rank(["a"], "z") is None


def test_committed_proposal_has_ten_items_of_each_kind() -> None:
    items = read_known_items((ROOT / "data/review/uu27-2022/known_items.md").read_text("utf-8"))
    assert len(items) == 10
    assert len({i.id for i in items}) == 10
    kinds = [i.kind for i in items]
    assert kinds.count("exact reference") == 2
    assert kinds.count("term") == 2
    assert kinds.count("Indonesian paraphrase") == 3
    assert kinds.count("English paraphrase") == 3
