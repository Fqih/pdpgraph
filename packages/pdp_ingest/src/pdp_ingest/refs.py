# SPDX-License-Identifier: Apache-2.0
"""`refs` stage (03 §5.1, M1.3, FR-PDP-03): reference mentions in unit text -> resolved targets.

A mention is one maximal chain of reference items, e.g. "sebagaimana dimaksud dalam Pasal 8,
Pasal 9, dan Pasal 13 ayat (1) dan ayat (2)". Items are "Pasal N [ayat (n)] [huruf x] [angka n]"
or start lower ("ayat (1)", "huruf a"), joined by ",", "dan", "atau", "dan/atau" (list) or
"sampai dengan" (range). Resolution:

- an item starting below Pasal takes the missing upper levels from the previous item in the
  chain, or, for the first item, from the context unit: the unit itself, or for a Penjelasan unit
  the unit it explains (`pj-umum` has no context);
- a range expands to every unit of the same kind between the endpoints (same parent; Pasal ranges
  follow document order across structures), one target per unit;
- a chain followed by "Undang-Undang ini" stays internal; one followed by an external instrument
  (UUD 1945, "Undang-Undang Nomor X Tahun Y", KUHP, Peraturan Pemerintah, ...) is
  EXTERNAL_UNRESOLVED and keeps the instrument;
- a target that does not exist leaves the mention UNRESOLVED with the item in `unresolved`.

Other mention kinds: "Undang-Undang ini" alone (SELF, no target), a bare external instrument
(EXTERNAL_UNRESOLVED), and delegation phrases "diatur dengan/dalam Peraturan ..." (kind
DELEGATION; no graph edge yet). Generic phrases that name no instrument ("peraturan
perundang-undangan", "ketentuan Undang-Undang") are not mentions.
"""

import re
from dataclasses import dataclass, field
from typing import NamedTuple

from common import ids
from pdp_ingest.segment import Unit, _label

_ITEM = re.compile(
    r"(?:Pasal\s+(?P<pasal>\d+)(?P<psuf>[A-Z]?)\b)?"
    r"(?:\s*ayat\s+\((?P<ayat>\d+)(?P<asuf>[a-z]?)\))?"
    r"(?:\s*huruf\s+(?P<huruf>[a-z])\b)?"
    r"(?:\s*angka\s+(?P<angka>\d+)\b)?"
)
_START = re.compile(r"\b(?:Pasal\s+\d|ayat\s+\(\d|huruf\s+[a-z]\b|angka\s+\d)")
_SEP = re.compile(
    r",\s*(?:dan/atau\s+|dan\s+|atau\s+)?"
    r"|\s+(?:dan/atau|dan|atau)\s+"
    r"|\s+(?P<range>sampai dengan)\s+"
)
_PREFIX = re.compile(r"sebagaimana dimaksud (?:dalam|pada)\s+$")
_INSTRUMENT = (
    r"(?:Undang-Undang Dasar Negara Republik Indonesia Tahun 1945"
    r"|Undang-Undang Nomor\s+\d+\s+Tahun\s+\d{4}"
    r"|Kitab Undang-Undang Hukum (?:Acara )?(?:Pidana|Perdata)"
    r"|KUHP(?:erdata)?\b"
    r"|Peraturan (?:Pemerintah|Presiden|Menteri|Daerah|Lembaga)(?:\s+Nomor\s+\d+\s+Tahun\s+\d{4})?)"
)
_SELF_QUAL = re.compile(r"\s+Undang-Undang ini\b")
_EXT_QUAL = re.compile(r"\s+(" + _INSTRUMENT + ")")
_EXT = re.compile(r"(?:sebagaimana dimaksud (?:dalam|pada)\s+)?(" + _INSTRUMENT + ")")
_DELEGATION = re.compile(
    r"diatur\s+(?:dengan|dalam)\s+"
    r"(Peraturan (?:Pemerintah|Presiden|Menteri|Daerah|Lembaga)|Undang-Undang(?! ini\b))\b"
)
_SELF = re.compile(r"Undang-Undang ini\b")

Num = tuple[int, str | None]  # number and suffix


class _Ref(NamedTuple):
    """A reference item; levels left out are None."""

    pasal: Num | None
    ayat: Num | None
    huruf: str | None
    angka: int | None


@dataclass(frozen=True)
class Mention:
    unit_id: str  # unit whose text contains the mention
    start: int  # char span in the unit text (overrides applied)
    end: int
    text: str
    kind: str  # REFERENCE | DELEGATION
    resolution: str  # EXACT | UNRESOLVED | SELF | EXTERNAL_UNRESOLVED
    targets: tuple[str, ...] = ()  # internal unit ids, ranges expanded, document order of mention
    instrument: str | None = None  # external or delegated instrument as written
    patterns: tuple[str, ...] = ()  # sampling strata (06 §2.9)
    unresolved: tuple[str, ...] = field(default=())  # internal items without a unit


def _path_of(unit_id: str | None) -> _Ref | None:
    if unit_id is None:
        return None
    parsed = ids.parse(unit_id)
    if not isinstance(parsed, ids.UnitId) or not isinstance(parsed.path, ids.PasalPath):
        return None
    p = parsed.path
    ayat = (p.ayat, p.ayat_suffix) if p.ayat is not None else None
    return _Ref((p.pasal, p.pasal_suffix), ayat, p.huruf, p.angka)


def _item(m: re.Match[str]) -> _Ref:
    g = m.groupdict()
    return _Ref(
        (int(g["pasal"]), g["psuf"].lower() or None) if g["pasal"] else None,
        (int(g["ayat"]), g["asuf"] or None) if g["ayat"] else None,
        g["huruf"],
        int(g["angka"]) if g["angka"] else None,
    )


def _inherit(item: _Ref, base: _Ref | None) -> _Ref | None:
    """Take the levels above the item's first level from `base`; None without a Pasal."""
    first = next(i for i, level in enumerate(item) if level is not None)
    if first and base is None:
        return None
    b = base or _Ref(None, None, None, None)
    full = _Ref(
        b.pasal if first > 0 else item.pasal,
        b.ayat if first > 1 else item.ayat,
        b.huruf if first > 2 else item.huruf,
        item.angka,
    )
    return full if full.pasal is not None else None


def _to_path(full: _Ref) -> ids.PasalPath:
    pasal, psuf = full.pasal or (0, None)
    ayat, asuf = full.ayat or (None, None)
    return ids.PasalPath(pasal, psuf, ayat, asuf, full.huruf, full.angka)


class _Resolver:
    def __init__(self, units: list[Unit]) -> None:
        self.body = {u.unit_id: u for u in units if u.kind != "PENJELASAN"}

    def _expand(self, first: str, last: str) -> list[str] | None:
        a, b = self.body[first], self.body[last]
        if a.kind != b.kind or (a.kind != "PASAL" and a.parent_id != b.parent_id):
            return None
        return [
            u.unit_id
            for u in self.body.values()
            if u.kind == a.kind
            and (a.kind == "PASAL" or u.parent_id == a.parent_id)
            and a.order <= u.order <= b.order
        ]

    def chain(
        self, source_id: str, items: list[tuple[re.Match[str], bool]], context: _Ref | None
    ) -> tuple[list[str], list[str]]:
        """(targets, unresolved labels) of a chain of (item match, joined by 'sampai dengan')."""
        targets: list[str] = []
        unresolved: list[str] = []
        prev: _Ref | None = context
        prev_id: str | None = None
        for k, (m, is_range) in enumerate(items):
            full = _inherit(_item(m), prev if k else context)
            if full is None:
                unresolved.append(" ".join(m.group(0).split()))
                prev, prev_id = None, None
                continue
            path = _to_path(full)
            uid = ids.format(ids.UnitId(source_id, path))
            if uid not in self.body:
                unresolved.append(_label(path))
            elif is_range and prev_id is not None and (span := self._expand(prev_id, uid)):
                targets += span
            else:
                targets.append(uid)
            prev, prev_id = full, (uid if uid in self.body else None)
        return list(dict.fromkeys(targets)), unresolved


def _overlaps(spans: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(start < e and s < end for s, e in spans)


def _chain_items(text: str, pos: int) -> tuple[list[tuple[re.Match[str], bool]], int]:
    m = _ITEM.match(text, pos)
    if m is None:  # pragma: no cover - every group is optional, so _ITEM always matches
        raise ValueError(pos)
    items, end = [(m, False)], m.end()
    while (sep := _SEP.match(text, end)) and _START.match(text, sep.end()):
        nxt = _ITEM.match(text, sep.end())
        if nxt is None or nxt.end() == sep.end():
            break
        items.append((nxt, sep.group("range") is not None))
        end = nxt.end()
    return items, end


def _unit_mentions(unit: Unit, source_id: str, resolver: _Resolver) -> list[Mention]:
    text = unit.text
    pj = ("penjelasan",) if unit.kind == "PENJELASAN" else ()
    context = _path_of(unit.parent_id if unit.kind == "PENJELASAN" else unit.unit_id)
    out: list[Mention] = []
    spans: list[tuple[int, int]] = []

    def add(m: Mention) -> None:
        out.append(m)
        spans.append((m.start, m.end))

    for d in _DELEGATION.finditer(text):
        add(
            Mention(
                unit.unit_id,
                d.start(),
                d.end(),
                d.group(0),
                "DELEGATION",
                "EXTERNAL_UNRESOLVED",
                (),
                d.group(1),
                ("delegation", *pj),
            )
        )
    for s in _START.finditer(text):
        if _overlaps(spans, s.start(), s.start() + 1):
            continue
        items, end = _chain_items(text, s.start())
        prefix = _PREFIX.search(text, 0, s.start())
        start = prefix.start() if prefix else s.start()
        tags = ["sebagaimana"] if prefix else []
        tags.append("absolute" if items[0][0].group("pasal") else "relative")
        if any(not r for _, r in items[1:]):
            tags.append("list")
        if any(r for _, r in items):
            tags.append("range")
        if ext := _EXT_QUAL.match(text, end):
            end = ext.end()
            add(
                Mention(
                    unit.unit_id,
                    start,
                    end,
                    text[start:end],
                    "REFERENCE",
                    "EXTERNAL_UNRESOLVED",
                    (),
                    ext.group(1),
                    (*tags, "external", *pj),
                )
            )
            continue
        if q := _SELF_QUAL.match(text, end):
            end = q.end()
        targets, unresolved = resolver.chain(source_id, items, context)
        add(
            Mention(
                unit.unit_id,
                start,
                end,
                text[start:end],
                "REFERENCE",
                "UNRESOLVED" if unresolved else "EXACT",
                tuple(targets),
                None,
                (*tags, *pj),
                tuple(unresolved),
            )
        )
    for e in _EXT.finditer(text):
        if not _overlaps(spans, e.start(), e.end()):
            prefixed = ("sebagaimana",) if e.start(1) > e.start() else ()
            add(
                Mention(
                    unit.unit_id,
                    e.start(),
                    e.end(),
                    e.group(0),
                    "REFERENCE",
                    "EXTERNAL_UNRESOLVED",
                    (),
                    e.group(1),
                    (*prefixed, "external", *pj),
                )
            )
    for m in _SELF.finditer(text):
        if not _overlaps(spans, m.start(), m.end()):
            add(
                Mention(
                    unit.unit_id,
                    m.start(),
                    m.end(),
                    m.group(0),
                    "REFERENCE",
                    "SELF",
                    patterns=("self", *pj),
                )
            )
    return sorted(out, key=lambda m: m.start)


def extract_refs(units: list[Unit]) -> list[Mention]:
    """All mentions, in unit order, then by position."""
    if not units:
        return []
    source_id = units[0].unit_id.split("/", 1)[0]
    resolver = _Resolver(units)
    return [m for u in units for m in _unit_mentions(u, source_id, resolver)]
