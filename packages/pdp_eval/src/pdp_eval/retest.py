# SPDX-License-Identifier: Apache-2.0
"""Annotation log and intra-annotator test-retest agreement (GUIDELINE §6, M1.7).

The labeling CLI appends one entry per labeling act to `annotation-log.jsonl` next to the
dataset. First-pass entries give the timestamp the >= 7-day rule needs; retest entries hold the
blind re-labels. Agreement compares each retest with the item's current gold label.
"""

import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from pdp_eval.golden import GoldenItem, Verdict

LOG_NAME = "annotation-log.jsonl"


class LogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str
    phase: Literal["first", "retest"]
    annotator: str
    at: datetime
    gold_verdict: Verdict
    gold_unit_ids: list[str]
    seed: int | None = None  # retest sample seed, for reproducibility


def log_path(dataset: Path) -> Path:
    return dataset.parent / LOG_NAME


def read_log(path: Path) -> list[LogEntry]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [LogEntry.model_validate_json(line) for line in lines if line.strip()]


def append_log(path: Path, entry: LogEntry) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(entry.model_dump_json() + "\n")


def eligible(
    items: list[GoldenItem], log: list[LogEntry], now: datetime, min_days: int
) -> list[str]:
    """Labeled items whose latest first-pass label is >= `min_days` old and not yet retested."""
    first: dict[str, datetime] = {}
    retested = set()
    for e in log:
        if e.phase == "first":
            first[e.item_id] = max(e.at, first.get(e.item_id, e.at))
        else:
            retested.add(e.item_id)
    cutoff = now - timedelta(days=min_days)
    return sorted(
        i.item_id
        for i in items
        if i.is_labeled
        and i.item_id in first
        and first[i.item_id] <= cutoff
        and i.item_id not in retested
    )


def sample(candidates: list[str], k: int, seed: int) -> list[str]:
    if len(candidates) < k:
        raise ValueError(f"only {len(candidates)} items eligible for retest, need {k}")
    return random.Random(seed).sample(sorted(candidates), k)  # noqa: S311 - reproducible sampling, not crypto


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    return 1.0 if not sa and not sb else len(sa & sb) / len(sa | sb)


def agreement(items: list[GoldenItem], log: list[LogEntry]) -> dict[str, object]:
    latest: dict[str, LogEntry] = {}
    for e in log:
        if e.phase == "retest":
            latest[e.item_id] = e
    pairs = [(i, latest[i.item_id]) for i in items if i.is_labeled and i.item_id in latest]
    n = len(pairs)
    return {
        "kind": "intra-annotator test-retest (single annotator; not inter-annotator kappa)",
        "items": n,
        "verdict_agreement_pct": (
            round(100 * sum(i.gold_verdict == e.gold_verdict for i, e in pairs) / n, 1)
            if n
            else None
        ),
        "mean_gold_unit_jaccard": (
            round(sum(jaccard(i.gold_unit_ids, e.gold_unit_ids) for i, e in pairs) / n, 3)
            if n
            else None
        ),
    }
