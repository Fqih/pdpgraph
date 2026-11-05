# SPDX-License-Identifier: Apache-2.0
"""Reference-sample commands for the labeling CLI (M1.3, 06 §2.9).

- `refs-sample`: build the item set from the current resolver output: every mention (a
  stratified first batch, then the rest) plus targeted and random negatives (once; refuses to
  overwrite an existing file);
- `refs-label`: show each mention in context with the proposed targets; the annotator marks
  correct / wrong (with the right targets) / not a reference, or for a negative sentence
  no reference / missed (with the missed targets);
- `refs-report`: precision and recall of the current resolver on the labels, overall (each item
  once), per overlapping pattern slice and per negative batch, with Wilson 95% intervals.

Targets are unit ids (the source prefix may be left out, e.g. `p20/a2`) or SELF, EXTERNAL,
DELEGATION. A "wrong" answer is either the full target list or `+id` / `-id` edits of the
proposal.
"""

import argparse
import hashlib
import subprocess
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from pdp_eval.refsample import (
    PATTERNS,
    PSEUDO_TARGETS,
    TRIGGERS,
    RefItem,
    build_sample,
    dump_ref_items,
    load_ref_items,
    negative_pools,
    score,
    wilson,
)
from pdp_ingest.refs import extract_refs

if TYPE_CHECKING:
    from pdp_eval.cli import Session

TARGETS = "recall >= 95%, precision >= 98% [TARGET] (target level; precision weighs more)"


def cmd_refs_sample(args: argparse.Namespace, s: "Session", _: Callable[[], datetime]) -> int:
    if args.file.exists():
        s.say(f"{args.file} exists; labels are never overwritten. Remove it to rebuild.")
        return 1
    mentions = extract_refs(s.law.units)
    items = build_sample(
        s.law.units,
        mentions,
        first=args.first,
        per_type=args.per_type,
        targeted=args.targeted,
        random_negatives=args.random_negatives,
        seed=args.seed,
    )
    dump_ref_items(args.file, items)
    population = Counter(p for m in mentions for p in m.patterns)
    first = Counter(p for i in items if i.batch == "stratified" for p in i.patterns)
    batches = Counter(i.batch for i in items)
    s.say(f"wrote {len(items)} items to {args.file} (seed {args.seed})")
    s.say(f"mentions: {batches['stratified']} in the first batch, {batches['rest']} after")
    for p in PATTERNS:
        s.say(f"  {p}: {first[p]} of {population[p]} in the first batch")
    targeted = [i for i in items if i.batch == "targeted"]
    triggers = Counter(t for i in targeted for t in i.patterns)
    s.say(
        f"targeted negatives: {len(targeted)} of {len(negative_pools(s.law.units, mentions)[0])} "
        "candidates (" + ", ".join(f"{t} {triggers[t]}" for t in TRIGGERS if triggers[t]) + ")"
    )
    s.say(f"random negatives: {batches['random']}")
    return 0


def _targets(s: "Session", item: RefItem, prompt: str) -> list[str]:
    source = item.unit_id.split("/", 1)[0]

    def norm(token: str) -> str:
        if token.upper() in PSEUDO_TARGETS:
            return token.upper()
        return token if token.startswith(f"{source}/") else f"{source}/{token}"

    while True:
        tokens = s.ask(prompt).replace(",", " ").split()
        edits = bool(tokens) and all(t[0] in "+-" for t in tokens)
        values = [norm(t.lstrip("+-")) for t in tokens]
        unknown = [v for v in values if v not in PSEUDO_TARGETS and not s.law.has_unit(v)]
        if unknown:
            s.say(f"not a unit of the source (see :show N): {', '.join(unknown)}")
            continue
        if not edits:
            out = list(dict.fromkeys(values))
        else:
            removed = {v for t, v in zip(tokens, values, strict=True) if t[0] == "-"}
            added = [v for t, v in zip(tokens, values, strict=True) if t[0] == "+"]
            out = [t for t in dict.fromkeys([*item.proposed, *added]) if t not in removed]
        if out:
            return out
        s.say("at least one target")


def _label_one(s: "Session", item: RefItem, annotator: str) -> RefItem | None:
    tags = ", ".join(item.patterns) or "no trigger"
    s.say(f"\n== {item.item_id}  [{item.batch} {item.kind}; {tags}]  {item.label} ({item.unit_id})")
    s.say(item.context)
    if item.kind == "mention":
        s.say("proposed: " + " ".join(item.proposed))
        answer = s.ask("c=correct, w=wrong targets, n=not a reference, empty=skip: ")
        verdicts = {"c": "correct", "w": "wrong", "n": "not_reference"}
    else:
        if item.triggers:
            s.say("no mention found at the [[marked]] words")
        answer = s.ask("n=no reference, m=missed reference(s), empty=skip: ")
        verdicts = {"n": "no_reference", "m": "missed"}
    if answer not in verdicts:
        return None
    verdict = verdicts[answer]
    gold: list[str] = []
    if verdict == "correct":
        gold = list(item.proposed)
    elif verdict in ("wrong", "missed"):
        gold = _targets(s, item, "right targets (ids or SELF/EXTERNAL/DELEGATION; +id/-id edits): ")
    note = s.ask("note (optional): ")
    data = item.model_dump() | {
        "verdict": verdict,
        "gold_targets": gold,
        "annotator": annotator,
        "notes": note or item.notes,
    }
    return RefItem.model_validate(data)


def cmd_refs_label(args: argparse.Namespace, s: "Session", _: Callable[[], datetime]) -> int:
    from pdp_eval.cli import QuitRequested

    items = load_ref_items(args.file)
    todo = [args.item] if args.item else [i.item_id for i in items if i.verdict is None]
    for item_id in todo:
        index = next((n for n, i in enumerate(items) if i.item_id == item_id), None)
        if index is None:
            s.say(f"no item {item_id}")
            return 1
        try:
            result = _label_one(s, items[index], args.annotator)
        except QuitRequested:
            break
        if result is None:
            continue
        items = [*items[:index], result, *items[index + 1 :]]
        dump_ref_items(args.file, items)
        s.say(f"saved {item_id}")
    s.say(f"labeled {sum(i.verdict is not None for i in items)} of {len(items)}")
    return 0


def _rate(k: int, n: int) -> str:
    interval = wilson(k, n)
    if interval is None:
        return "-"
    lo, hi = interval
    return f"{100 * k / n:.1f}% [{100 * lo:.1f}-{100 * hi:.1f}]"


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def cmd_refs_report(args: argparse.Namespace, s: "Session", _: Callable[[], datetime]) -> int:
    items = load_ref_items(args.file)
    rows = score(items, extract_refs(s.law.units))
    digest = hashlib.sha256(args.file.read_bytes()).hexdigest()[:12]
    labeled = sum(i.verdict is not None for i in items)
    lines = [
        f"# Reference resolver report: {s.law.source_id}",
        "",
        f"Dataset `{args.file}` (sha256 {digest}); git {_git_sha()}; resolver is deterministic "
        f"(hardware-independent). Labeled: {labeled} of {len(items)}.",
        "",
        f"Targets: {TARGETS}.",
        "",
        "`overall` counts each item once (the headline); `mentions` each mention once; the "
        "pattern rows are overlapping slices (a mention can be both `sebagaimana` and "
        "`relative`). Precision and recall are target-level with Wilson 95% intervals, which "
        "treat targets as independent; `Exact` is the share of items whose targets all match.",
        "",
        "| Row | Items | Exact | TP | FP | FN | Precision | Recall |",
        "|---|---|---|---|---|---|---|---|",
    ]
    order = ("overall", "mentions", *PATTERNS, "negatives:targeted", "negatives:random")
    for key in order:
        if key in rows:
            r = {
                k: int(v or 0)
                for k, v in rows[key].items()
                if k in ("items", "exact", "tp", "fp", "fn")
            }
            lines.append(
                f"| {key} | {r['items']} | {_rate(r['exact'], r['items'])} | {r['tp']} | "
                f"{r['fp']} | {r['fn']} | {_rate(r['tp'], r['tp'] + r['fp'])} | "
                f"{_rate(r['tp'], r['tp'] + r['fn'])} |"
            )
    text = "\n".join(lines) + "\n"
    s.say(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    return 0


def add_parsers(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    from pathlib import Path

    default = Path("evals/datasets/pdp-refs/v0/sample.jsonl")
    sample = sub.add_parser("refs-sample")
    sample.add_argument("--file", type=Path, default=default)
    sample.add_argument("--first", type=int, default=50, help="stratified first batch")
    sample.add_argument("--per-type", type=int, default=5)
    sample.add_argument("--targeted", type=int, default=40)
    sample.add_argument("--random-negatives", type=int, default=10)
    sample.add_argument("--seed", type=int, default=20261105)
    sample.set_defaults(fn=cmd_refs_sample)
    label = sub.add_parser("refs-label")
    label.add_argument("--file", type=Path, default=default)
    label.add_argument("--annotator", default="faqih")
    label.add_argument("--item", help="(re-)label one item")
    label.set_defaults(fn=cmd_refs_label)
    report = sub.add_parser("refs-report")
    report.add_argument("--file", type=Path, default=default)
    report.add_argument("--out", type=Path)
    report.set_defaults(fn=cmd_refs_report)
