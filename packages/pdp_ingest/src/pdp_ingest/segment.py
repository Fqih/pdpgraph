# SPDX-License-Identifier: Apache-2.0
"""`segment` stage (03 §5.1, M1.2, FR-PDP-01): canonical body blocks -> structure + legal units.

A line-pattern state machine over the extracted blocks:

- preamble (until the first BAB) and the closing formula ("Agar setiap orang mengetahuinya ...")
  are not units;
- `BAB <roman>`, `Bagian <ordinal>`, `Paragraf <n>` open structures; the next block is the heading;
- `Pasal <n>[A]` opens a Pasal. Ayat/huruf/angka come from list nesting with the drafting
  convention (UU 12/2011): a Pasal whose first block is a list item lists ayat (then huruf, then
  angka); a Pasal with intro text lists huruf, or angka after "yang dimaksud dengan:";
- the Penjelasan (from the registry's explanation marker) yields `pj-umum` and one `#pj` unit
  per "Pasal N" / "Ayat (n)" / "Huruf x" / "Angka n" header, mapped to the explained unit.

Unit text is the unit's own text, without its children; continuation blocks join with "\\n".
Ids are built and rendered by `common.ids`. Manual fixes are applied afterwards (`overrides`).
"""

import re
from dataclasses import dataclass, field, replace

from common import ids
from pdp_ingest.canonical import Block

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_ORDINALS = {
    w: n
    for n, w in enumerate(
        [
            "Kesatu",
            "Kedua",
            "Ketiga",
            "Keempat",
            "Kelima",
            "Keenam",
            "Ketujuh",
            "Kedelapan",
            "Kesembilan",
            "Kesepuluh",
        ],
        start=1,
    )
}
_BAB = re.compile(r"BAB ([IVXLC]+)")
_BAGIAN = re.compile(r"Bagian (" + "|".join(_ORDINALS) + ")")
_PARAGRAF = re.compile(r"Paragraf (\d+)")
_PASAL = re.compile(r"Pasal (\d+)([A-Z]?)")
_CLOSING = re.compile(r"Agar setiap orang mengetahuinya\b.*")
_PJ_UMUM = re.compile(r"I\.? UMUM")
_PJ_PASAL_DEMI_PASAL = re.compile(r"II\.? PASAL DEMI PASAL")
_PJ_AYAT = re.compile(r"Ayat \(?(\d+)([a-z]?)\)?")
_PJ_HURUF = re.compile(r"Huruf ([a-z]+)")
_PJ_ANGKA = re.compile(r"Angka (\d+)")


class SegmentError(Exception):
    """The body does not follow the expected structure."""


@dataclass(frozen=True)
class Structure:
    unit_id: str
    kind: str  # BAB | BAGIAN | PARAGRAF
    number: int
    heading: str
    parent_id: str | None
    order: int


@dataclass(frozen=True)
class Unit:
    unit_id: str
    kind: str  # PASAL | AYAT | HURUF | ANGKA | PENJELASAN
    label: str
    text: str
    parent_id: str | None  # structure for a Pasal, Pasal/ayat/huruf above, explained unit for pj
    order: int
    depth: int = 0  # list depth inside the Pasal (0 = the Pasal itself)


@dataclass
class Segmented:
    structures: list[Structure] = field(default_factory=list)
    units: list[Unit] = field(default_factory=list)

    def by_id(self) -> dict[str, Unit]:
        return {u.unit_id: u for u in self.units}


def roman(numeral: str) -> int:
    values = [_ROMAN[c] for c in numeral]
    return sum(-v if v < nxt else v for v, nxt in zip(values, [*values[1:], 0], strict=True))


def _fmt(source_id: str, path: ids.PasalPath | ids.PjUmum, pj: bool = False) -> str:
    return ids.format(ids.UnitId(source_id, path, penjelasan=pj))


def _label(path: ids.PasalPath) -> str:
    out = f"Pasal {path.pasal}{(path.pasal_suffix or '').upper()}"
    if path.ayat is not None:
        out += f" ayat ({path.ayat}{path.ayat_suffix or ''})"
    if path.huruf is not None:
        out += f" huruf {path.huruf}"
    if path.angka is not None:
        out += f" angka {path.angka}"
    return out


def _letter(index: int) -> str:
    if not 1 <= index <= 26:
        raise SegmentError(f"huruf index {index} out of range")
    return chr(ord("a") + index - 1)


_KIND = {"a": "AYAT", "h": "HURUF", "n": "ANGKA"}


def _list_path(pasal: ids.PasalPath, kinds: str, path: tuple[int, ...]) -> ids.PasalPath:
    if len(path) > 3:
        raise SegmentError(f"{_label(pasal)}: list nesting deeper than 3 at {path}")
    parts: dict[str, int | str] = {}
    for depth, index in enumerate(path):
        kind = kinds[depth]
        key = {"a": "ayat", "h": "huruf", "n": "angka"}[kind]
        if key in parts:
            raise SegmentError(f"{_label(pasal)}: two {key} levels at {path}")
        parts[key] = _letter(index) if kind == "h" else index
    return replace(pasal, **parts)  # type: ignore[arg-type]


class _Body:
    """State for the batang tubuh."""

    def __init__(self, source_id: str, out: Segmented) -> None:
        self.source_id, self.out = source_id, out
        self.bab: str | None = None
        self.bagian: str | None = None
        self.paragraf: str | None = None
        self.pending_heading: Structure | None = None
        self.pasal: ids.PasalPath | None = None
        self.kinds = ""
        self.texts: dict[str, list[str]] = {}
        self.meta: dict[
            str, tuple[str, str, str | None, int]
        ] = {}  # id -> kind, label, parent, depth
        self.order: list[str] = []
        self.seen_pasal: set[str] = set()

    def _structure(self, kind: str, number: int, unit_id: str, parent: str | None) -> None:
        self.pending_heading = Structure(
            unit_id, kind, number, "", parent, len(self.out.structures)
        )
        self.pasal = None

    def _add(self, unit_id: str, kind: str, label: str, parent: str | None, depth: int) -> None:
        if unit_id in self.meta:
            raise SegmentError(f"duplicate unit {unit_id}")
        self.meta[unit_id] = (kind, label, parent, depth)
        self.texts[unit_id] = []
        self.order.append(unit_id)

    def feed(self, b: Block) -> None:
        if self.pending_heading is not None and not b.path:
            self.out.structures.append(replace(self.pending_heading, heading=b.text))
            self.pending_heading = None
            return
        if not b.path and (m := _BAB.fullmatch(b.text)):
            n = roman(m.group(1))
            self.bab, self.bagian, self.paragraf = f"{self.source_id}/bab{n}", None, None
            self._structure("BAB", n, self.bab, None)
            return
        if not b.path and (m := _BAGIAN.fullmatch(b.text)):
            n = _ORDINALS[m.group(1)]
            self.bagian, self.paragraf = f"{self.bab}/bag{n}", None
            self._structure("BAGIAN", n, self.bagian, self.bab)
            return
        if not b.path and (m := _PARAGRAF.fullmatch(b.text)):
            n = int(m.group(1))
            self.paragraf = f"{self.bagian}/par{n}"
            self._structure("PARAGRAF", n, self.paragraf, self.bagian)
            return
        if not b.path and (m := _PASAL.fullmatch(b.text)):
            self.pasal = ids.PasalPath(int(m.group(1)), m.group(2).lower() or None)
            self.kinds = ""
            pid = _fmt(self.source_id, self.pasal)
            self._add(pid, "PASAL", _label(self.pasal), self.paragraf or self.bagian or self.bab, 0)
            return
        if self.pasal is None:
            raise SegmentError(f"text outside a Pasal: {b.text[:60]!r}")
        pid = _fmt(self.source_id, self.pasal)
        if not self.kinds:
            if not b.path:
                intro = b.text.endswith("yang dimaksud dengan:")
                self.kinds = "nnn" if intro else "hnn"
            else:
                self.kinds = "ahn"
        if not b.path:
            self.texts[pid].append(b.text)
            return
        path = _list_path(self.pasal, self.kinds, b.path)
        uid = _fmt(self.source_id, path)
        if b.list_item_start:
            parent = _fmt(self.source_id, _list_path(self.pasal, self.kinds, b.path[:-1]))
            self._add(uid, _KIND[self.kinds[len(b.path) - 1]], _label(path), parent, len(b.path))
        elif uid not in self.texts:
            raise SegmentError(f"continuation before list item: {b.text[:60]!r}")
        self.texts[uid].append(b.text)

    def finish(self, start: int) -> int:
        for n, uid in enumerate(self.order, start=start):
            kind, label, parent, depth = self.meta[uid]
            text = "\n".join(self.texts[uid])
            self.out.units.append(Unit(uid, kind, label, text, parent, n, depth))
        return start + len(self.order)


def _penjelasan(source_id: str, part: list[Block], body: dict[str, Unit], start: int) -> list[Unit]:
    units: list[Unit] = []
    texts: dict[str, list[str]] = {}
    order: list[tuple[str, str]] = []  # (pj id, explained id)
    current: str | None = None
    pasal: ids.PasalPath | None = None
    ayat: ids.PasalPath | None = None
    huruf: ids.PasalPath | None = None
    section = "title"

    def open_(path: ids.PasalPath | ids.PjUmum) -> str:
        explained = _fmt(source_id, path)
        if not isinstance(path, ids.PjUmum) and explained not in body:
            raise SegmentError(f"Penjelasan header for missing unit {explained}")
        pj = explained if isinstance(path, ids.PjUmum) else _fmt(source_id, path, pj=True)
        if pj in texts:
            raise SegmentError(f"duplicate Penjelasan header for {explained}")
        texts[pj] = []
        order.append((pj, explained))
        return pj

    for b in part:
        t = b.text
        if section == "title":
            if _PJ_UMUM.fullmatch(t):
                section, current = "umum", open_(ids.PjUmum())
            continue
        if _PJ_PASAL_DEMI_PASAL.fullmatch(t):
            section, current = "pasal", None
            continue
        if section == "pasal" and (m := _PASAL.fullmatch(t)):
            pasal = ids.PasalPath(int(m.group(1)), m.group(2).lower() or None)
            ayat = huruf = None
            current = open_(pasal)
            continue
        if section == "pasal" and pasal is not None and (m := _PJ_AYAT.fullmatch(t)):
            ayat = replace(pasal, ayat=int(m.group(1)), ayat_suffix=m.group(2) or None)
            huruf = None
            current = open_(ayat)
            continue
        if section == "pasal" and pasal is not None and (m := _PJ_HURUF.fullmatch(t)):
            huruf = replace(ayat or pasal, huruf=m.group(1))
            current = open_(huruf)
            continue
        if section == "pasal" and pasal is not None and (m := _PJ_ANGKA.fullmatch(t)):
            current = open_(replace(huruf or ayat or pasal, angka=int(m.group(1))))
            continue
        if current is None:
            raise SegmentError(f"Penjelasan text without a header: {t[:60]!r}")
        texts[current].append(t)
    for n, (pj, explained) in enumerate(order, start=start):
        text = "\n".join(texts[pj])
        if not text:
            continue  # a header followed directly by sub-headers carries no text of its own
        label = (
            "Penjelasan Umum"
            if explained.endswith("pj-umum")
            else ("Penjelasan " + body[explained].label)
        )
        parent = None if explained.endswith("pj-umum") else explained
        units.append(Unit(pj, "PENJELASAN", label, text, parent, n))
    return units


def segment(source_id: str, body: list[Block], *, explanation_marker: str) -> Segmented:
    split = next(
        (i for i, b in enumerate(body) if not b.path and b.text == explanation_marker), None
    )
    if split is None:
        raise SegmentError(f"explanation marker {explanation_marker!r} not found")
    out = Segmented()
    state = _Body(source_id, out)
    started = False
    for b in body[:split]:
        if not started:
            started = not b.path and _BAB.fullmatch(b.text) is not None
            if not started:
                continue  # preamble
        if not b.path and _CLOSING.fullmatch(b.text):
            break
        state.feed(b)
    next_order = state.finish(0)
    out.units.extend(_penjelasan(source_id, body[split + 1 :], out.by_id(), next_order))
    return out
