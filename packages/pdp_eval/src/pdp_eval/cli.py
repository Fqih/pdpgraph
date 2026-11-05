# SPDX-License-Identifier: Apache-2.0
"""Labeling CLI for `pdp-golden` (M1.7): `uv run python -m pdp_eval <command>`.

Commands: `validate`, `show`, `label`, `relabel` (blind test-retest), `agreement`, and the
reference-sample commands `refs-sample`, `refs-label`, `refs-report` (`refs_cli.py`).
Gold fields are only ever written from what the annotator types; nothing is pre-filled.
At any prompt: `:show 46` prints Pasal 46 and its Penjelasan, `:umum` the Penjelasan Umum,
`:quit` stops (labels already saved stay saved).
"""

import argparse
import json
import secrets
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from pdp_eval.golden import VERDICTS, GoldenItem, composition, dump_items, load_items
from pdp_eval.law import LawText
from pdp_eval.refs_cli import add_parsers as add_refs_parsers
from pdp_eval.retest import LogEntry, agreement, append_log, eligible, log_path, read_log, sample
from pdp_eval.terms_cli import add_parsers as add_terms_parsers

Ask = Callable[[str], str]


class QuitRequested(Exception):  # noqa: N818 - control flow, not an error
    """Annotator typed :quit."""


class Session:
    def __init__(self, law: LawText, ask: Ask, out: TextIO) -> None:
        self.law, self._ask, self.out = law, ask, out

    def say(self, text: str = "") -> None:
        print(text, file=self.out)

    def show(self, arg: str) -> None:
        if arg == "umum":
            self.say("\n".join(["Penjelasan Umum:", *self.law.general_explanation()]))
            return
        try:
            lines = self.law.pasal(int(arg))
        except (ValueError, KeyError):
            self.say(f"no Pasal {arg!r}")
            return
        for line in lines:
            indent = "  " * line.depth
            text = line.text.replace("\n", "\n" + indent + "  ")
            self.say(f"{indent}{line.label} {text}".rstrip() + f"   [{line.unit_id or ''}]")
        self.say("  Penjelasan: " + " / ".join(self.law.explanation(int(arg))))

    def ask(self, prompt: str) -> str:
        while True:
            answer = self._ask(prompt).strip()
            if answer == ":quit":
                raise QuitRequested
            if answer == ":umum":
                self.show("umum")
            elif answer.startswith(":show"):
                self.show(answer.removeprefix(":show").strip())
            else:
                return answer

    def verdict(self) -> str | None:
        """A verdict, or None to skip; 'drop' is passed through."""
        menu = "  ".join(f"{n}={v}" for n, v in enumerate(VERDICTS, start=1))
        while True:
            answer = self.ask(f"verdict ({menu}; empty=skip, drop=remove item): ")
            if answer in ("", "drop"):
                return answer or None
            if answer.isdigit() and 1 <= int(answer) <= len(VERDICTS):
                return VERDICTS[int(answer) - 1]
            if answer in VERDICTS:
                return answer
            self.say("unknown verdict")

    def units(self, prompt: str, *, required: bool) -> list[str]:
        while True:
            raw = self.ask(prompt)
            values = [v for v in raw.replace(",", " ").split() if v]
            unknown = [v for v in values if not self.law.has_unit(v)]
            if unknown:
                self.say(f"not a unit of the source (see :show N): {', '.join(unknown)}")
            elif required and not values:
                self.say("at least one unit is required for this verdict")
            else:
                return values

    def points(self) -> list[str]:
        self.say("answer points, one per line; empty line ends:")
        out: list[str] = []
        while True:
            line = self.ask("  - ")
            if not line:
                if out:
                    return out
                self.say("at least one answer point")
                continue
            out.append(line)


def _header(s: Session, item: GoldenItem, *, blind: bool) -> None:
    s.say(f"\n== {item.item_id}  [{item.category}, {item.language}, hops={item.hops}]")
    s.say(f"as_of: {item.as_of}")
    s.say(f"Q: {item.question}")
    if not blind and item.notes:
        s.say(f"notes: {item.notes}")
    if not blind and item.is_labeled:
        s.say(f"current: {item.gold_verdict} {item.gold_unit_ids} {item.gold_answer_points}")


def _label_one(s: Session, item: GoldenItem, annotator: str) -> GoldenItem | str | None:
    _header(s, item, blind=False)
    verdict = s.verdict()
    if verdict is None or verdict == "drop":
        return verdict
    gold = s.units(
        "gold units (space/comma separated): ", required=verdict != "INSUFFICIENT_EVIDENCE"
    )
    acceptable = s.units("acceptable units (optional): ", required=False)
    points = s.points()
    hops = s.ask(f"hops = distinct Pasal needed [{item.hops}]: ") or str(item.hops)
    as_of = s.ask(f"as_of [{item.as_of}]: ") or str(item.as_of)
    note = s.ask("note (optional): ")
    notes = f"{item.notes} | {annotator}: {note}".strip(" |") if note else item.notes
    data: dict[str, Any] = item.model_dump() | {
        "gold_verdict": verdict,
        "gold_unit_ids": gold,
        "acceptable_unit_ids": acceptable,
        "gold_answer_points": points,
        "hops": int(hops) if hops.isdigit() else hops,
        "as_of": as_of,
        "annotator": annotator,
        "notes": notes,
    }
    try:
        return GoldenItem.model_validate(data)
    except ValueError as exc:
        s.say(f"not saved: {exc}")
        return None


def cmd_label(args: argparse.Namespace, s: Session, now: Callable[[], datetime]) -> int:
    items = load_items(args.file)
    todo = [i.item_id for i in items if (args.item is None and not i.is_labeled)]
    todo = [args.item] if args.item else todo
    for item_id in todo:
        index = next((n for n, i in enumerate(items) if i.item_id == item_id), None)
        if index is None:
            s.say(f"no item {item_id}")
            return 1
        try:
            result = _label_one(s, items[index], args.annotator)
        except QuitRequested:
            break
        if result == "drop":
            if s.ask(f"remove {item_id} from {args.file.name}? (yes/no): ") == "yes":
                items = items[:index] + items[index + 1 :]
                dump_items(args.file, items)
            continue
        if not isinstance(result, GoldenItem):
            continue
        items = [*items[:index], result, *items[index + 1 :]]
        dump_items(args.file, items)
        append_log(
            log_path(args.file),
            LogEntry(
                item_id=item_id,
                phase="first",
                annotator=args.annotator,
                at=now(),
                gold_verdict=result.gold_verdict,
                gold_unit_ids=result.gold_unit_ids,
            ),
        )
        s.say(f"saved {item_id}")
    s.say(json.dumps(composition(items)))
    return 0


def cmd_relabel(args: argparse.Namespace, s: Session, now: Callable[[], datetime]) -> int:
    """Blind re-label: shows only the question and the law text, never earlier labels."""
    items = {i.item_id: i for i in load_items(args.file)}
    path = log_path(args.file)
    log = read_log(path)
    seed = args.seed if args.seed is not None else secrets.randbelow(2**31)
    pending = eligible(list(items.values()), log, now(), args.min_days)
    try:
        chosen = sample(pending, args.sample, seed)
    except ValueError as exc:
        s.say(f"{exc} (labeled >= {args.min_days} days ago and not yet retested)")
        return 1
    s.say(f"blind re-label of {len(chosen)} items, seed {seed}")
    for item_id in chosen:
        _header(s, items[item_id], blind=True)
        try:
            verdict = None
            while verdict in (None, "drop"):
                verdict = s.verdict()
            gold = s.units("gold units: ", required=verdict != "INSUFFICIENT_EVIDENCE")
        except QuitRequested:
            break
        entry = LogEntry(
            item_id=item_id,
            phase="retest",
            annotator=args.annotator,
            at=now(),
            gold_verdict=verdict,
            gold_unit_ids=gold,
            seed=seed,
        )
        append_log(path, entry)
        s.say(f"recorded {item_id}")
    return 0


def cmd_agreement(args: argparse.Namespace, s: Session, _: Callable[[], datetime]) -> int:
    s.say(json.dumps(agreement(load_items(args.file), read_log(log_path(args.file))), indent=2))
    return 0


def cmd_validate(args: argparse.Namespace, s: Session, _: Callable[[], datetime]) -> int:
    items = load_items(args.file)
    unknown = [
        (i.item_id, u)
        for i in items
        for u in [*i.gold_unit_ids, *i.acceptable_unit_ids]
        if not s.law.has_unit(u)
    ]
    s.say(json.dumps(composition(items), indent=2))
    for item_id, unit in unknown:
        s.say(f"{item_id}: unknown unit {unit}")
    return 1 if unknown else 0


def cmd_show(args: argparse.Namespace, s: Session, _: Callable[[], datetime]) -> int:
    s.show(args.pasal)
    return 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pdp_eval", description=__doc__)
    p.add_argument("--source", default="uu27-2022")
    p.add_argument("--registry", type=Path, default=Path("configs/sources"))
    p.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    p.add_argument("--overrides-dir", type=Path, default=Path("data/overrides"))
    sub = p.add_subparsers(dest="command", required=True)
    default_file = Path("evals/datasets/pdp-golden/v0/dev.jsonl")
    for name, fn in (
        ("validate", cmd_validate),
        ("label", cmd_label),
        ("relabel", cmd_relabel),
        ("agreement", cmd_agreement),
    ):
        c = sub.add_parser(name)
        c.add_argument("--file", type=Path, default=default_file)
        c.set_defaults(fn=fn)
        if name in ("label", "relabel"):
            c.add_argument("--annotator", default="faqih")
    sub.choices["label"].add_argument("--item", help="(re-)label one item, showing its labels")
    sub.choices["relabel"].add_argument("--sample", type=int, default=20)
    sub.choices["relabel"].add_argument("--seed", type=int)
    sub.choices["relabel"].add_argument("--min-days", type=int, default=7)
    show = sub.add_parser("show")
    show.add_argument("pasal", help="Pasal number or 'umum'")
    show.set_defaults(fn=cmd_show)
    add_refs_parsers(sub)
    add_terms_parsers(sub)
    return p


def main(
    argv: list[str] | None = None,
    *,
    ask: Ask = input,
    out: TextIO = sys.stdout,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    law: LawText | None = None,
) -> int:
    args = _parser().parse_args(argv)
    law = law or LawText.from_source(args.source, args.registry, args.raw_dir, args.overrides_dir)
    fn: Callable[[argparse.Namespace, Session, Callable[[], datetime]], int] = args.fn
    return fn(args, Session(law, ask, out), now)
