# SPDX-License-Identifier: Apache-2.0
"""Term-link sample commands for the labeling CLI (M1.4, 06 §2.10).

- `terms-sample`: build the item set from the current linker (once; refuses to overwrite);
- `terms-label`: show each link in context with its term; the annotator marks it correct or
  wrong (for an informal match: does the text use the defined term?);
- `terms-report`: link precision of the current linker on the labels, for defined links,
  per term, and for informal matches, with Wilson 95% intervals.
"""

import argparse
import hashlib
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from pdp_eval.refs_cli import _git_sha, _rate
from pdp_eval.termsample import (
    TermItem,
    build_term_sample,
    dump_term_items,
    load_term_items,
    score_terms,
)
from pdp_ingest.defs import Definition, TermUse, extract_definitions, link_terms
from pdp_ingest.refs import extract_refs

if TYPE_CHECKING:
    from pdp_eval.cli import Session

_QUESTION = {
    "defined": "does every [[marked]] occurrence use the defined term?",
    "informal": "does this lowercase [[match]] use the defined term?",
}


def _current(s: "Session") -> tuple[list[Definition], list[TermUse]]:
    units = s.law.units
    defs = extract_definitions(units)
    return defs, link_terms(units, defs, extract_refs(units))


def cmd_terms_sample(args: argparse.Namespace, s: "Session", _: Callable[[], datetime]) -> int:
    if args.file.exists():
        s.say(f"{args.file} exists; labels are never overwritten. Remove it to rebuild.")
        return 1
    defs, uses = _current(s)
    items = build_term_sample(
        s.law.units, defs, uses, defined=args.defined, informal=args.informal, seed=args.seed
    )
    dump_term_items(args.file, items)
    population = Counter(u.kind for u in uses)
    sampled = Counter(i.kind for i in items)
    s.say(f"wrote {len(items)} items to {args.file} (seed {args.seed})")
    for kind in ("defined", "informal"):
        terms = len({i.term for i in items if i.kind == kind})
        s.say(f"  {kind}: {sampled[kind]} of {population[kind]} links, {terms} terms")
    return 0


def _label_one(s: "Session", item: TermItem, annotator: str) -> TermItem | None:
    s.say(f"\n== {item.item_id}  [{item.kind}] {item.term}  {item.label} ({item.unit_id})")
    s.say(item.context)
    answer = s.ask(f"{_QUESTION[item.kind]} c=correct, w=wrong, empty=skip: ")
    verdicts = {"c": "correct", "w": "wrong"}
    if answer not in verdicts:
        return None
    note = s.ask("note (optional): ")
    data = item.model_dump() | {
        "verdict": verdicts[answer],
        "annotator": annotator,
        "notes": note or item.notes,
    }
    return TermItem.model_validate(data)


def cmd_terms_label(args: argparse.Namespace, s: "Session", _: Callable[[], datetime]) -> int:
    from pdp_eval.cli import QuitRequested

    items = load_term_items(args.file)
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
        dump_term_items(args.file, items)
        s.say(f"saved {item_id}")
    s.say(f"labeled {sum(i.verdict is not None for i in items)} of {len(items)}")
    return 0


def cmd_terms_report(args: argparse.Namespace, s: "Session", _: Callable[[], datetime]) -> int:
    items = load_term_items(args.file)
    uses = _current(s)[1]
    rows = score_terms(items, uses)
    digest = hashlib.sha256(args.file.read_bytes()).hexdigest()[:12]
    labeled = sum(i.verdict is not None for i in items)
    lines = [
        f"# Term-link report: {s.law.source_id}",
        "",
        f"Dataset `{args.file}` (sha256 {digest}); git {_git_sha()}; linker is deterministic "
        f"(hardware-independent). Labeled: {labeled} of {len(items)}.",
        "",
        "`defined` rows are `USES_TERM` edges: precision = correct / labeled. `informal` is the "
        "share of lowercase matches that do use the defined term (they are not edges). `term:` "
        "rows slice the defined links. `stale` links are no longer produced by the linker and "
        "are not scored. Wilson 95% intervals.",
        "",
        "| Row | Items | Correct | Rate |",
        "|---|---|---|---|",
    ]
    order = ["defined", *sorted(k for k in rows if k.startswith("term:")), "informal", "stale"]
    for key in order:
        if key in rows:
            r = rows[key]
            lines.append(
                f"| {key} | {r['items']} | {r['correct']} | {_rate(r['correct'], r['items'])} |"
            )
    text = "\n".join(lines) + "\n"
    s.say(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    return 0


def add_parsers(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    from pathlib import Path

    default = Path("evals/datasets/pdp-terms/v0/sample.jsonl")
    sample = sub.add_parser("terms-sample")
    sample.add_argument("--file", type=Path, default=default)
    sample.add_argument("--defined", type=int, default=30)
    sample.add_argument("--informal", type=int, default=10)
    sample.add_argument("--seed", type=int, default=20261105)
    sample.set_defaults(fn=cmd_terms_sample)
    label = sub.add_parser("terms-label")
    label.add_argument("--file", type=Path, default=default)
    label.add_argument("--annotator", default="faqih")
    label.add_argument("--item", help="(re-)label one item")
    label.set_defaults(fn=cmd_terms_label)
    report = sub.add_parser("terms-report")
    report.add_argument("--file", type=Path, default=default)
    report.add_argument("--out", type=Path)
    report.set_defaults(fn=cmd_terms_report)
