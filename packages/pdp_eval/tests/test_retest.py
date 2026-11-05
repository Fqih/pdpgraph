# SPDX-License-Identifier: Apache-2.0
"""Test-retest selection and agreement (GUIDELINE §6, M1.7)."""

from datetime import UTC, datetime, timedelta

import pytest

from pdp_eval.golden import GoldenItem
from pdp_eval.retest import LogEntry, eligible, jaccard, sample

T0 = datetime(2026, 11, 5, tzinfo=UTC)


def _item(item_id: str, *, labeled: bool) -> GoldenItem:
    gold = {
        "gold_verdict": "INFORMATIONAL",
        "gold_unit_ids": ["uu27-2022/p1"],
        "gold_answer_points": ["x"],
        "annotator": "faqih",
    }
    base = {
        "schema_version": 1,
        "item_id": item_id,
        "question": "q",
        "language": "id",
        "as_of": "2026-11-05",
        "category": "scope",
        "hops": 1,
    }
    return GoldenItem.model_validate(base | (gold if labeled else {}))


def _entry(item_id: str, phase: str, at: datetime) -> LogEntry:
    return LogEntry.model_validate(
        {
            "item_id": item_id,
            "phase": phase,
            "annotator": "faqih",
            "at": at,
            "gold_verdict": "INFORMATIONAL",
            "gold_unit_ids": [],
        }
    )


def test_eligible_uses_latest_first_pass_and_skips_unlabeled_and_retested() -> None:
    items = [_item(f"g-000{n}", labeled=n != 4) for n in range(1, 5)]
    log = [
        _entry("g-0001", "first", T0),
        _entry("g-0002", "first", T0),
        _entry("g-0002", "first", T0 + timedelta(days=3)),  # edited later: clock restarts
        _entry("g-0003", "first", T0),
        _entry("g-0003", "retest", T0 + timedelta(days=8)),
        _entry("g-0004", "first", T0),
    ]
    assert eligible(items, log, T0 + timedelta(days=7), 7) == ["g-0001"]
    assert eligible(items, log, T0 + timedelta(days=10), 7) == ["g-0001", "g-0002"]


def test_sample_is_reproducible_by_seed() -> None:
    ids = [f"g-{n:04d}" for n in range(1, 51)]
    assert sample(ids, 20, 42) == sample(list(reversed(ids)), 20, 42)
    assert sample(ids, 20, 42) != sample(ids, 20, 43)
    assert len(set(sample(ids, 20, 42))) == 20


def test_sample_needs_enough_items() -> None:
    with pytest.raises(ValueError, match="only 3 items eligible for retest, need 20"):
        sample(["a", "b", "c"], 20, 1)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [([], [], 1.0), (["x"], ["x"], 1.0), (["x"], ["y"], 0.0), (["x", "y"], ["x"], 0.5)],
)
def test_jaccard(a: list[str], b: list[str], expected: float) -> None:
    assert jaccard(a, b) == expected
