# SPDX-License-Identifier: Apache-2.0
"""`defs` stage (03 §5.1, M1.4, FR-PDP-04): Pasal 1 definitions, term usage, data categories.

Definitions: every item of the definitional Pasal ("Dalam Undang-Undang ini yang dimaksud
dengan:") reads "<term> [yang selanjutnya disebut|disingkat <alias>] adalah <definiens>". The
term gets a slug via `common.ids.assign_slugs` (04 §2.1); `text` is the whole item as written.

Usage linking, per unit (Penjelasan included):

1. defined usage: occurrences of a term or alias with its capitalization, longest first, not
   overlapping each other ("Data Pribadi yang bersifat spesifik" before "Data Pribadi"). A
   trailing enclitic "-nya" is part of the occurrence. These become `USES_TERM` edges.
2. informal usage: case-insensitive occurrences that differ in capitalization ("data pribadi",
   "subjek Data Pribadi"), longest first, not overlapping each other and not inside a defined
   occurrence. A defined occurrence may sit inside an informal one ("subjek Data Pribadi" keeps
   its defined "Data Pribadi"). Recorded with low confidence; no edge.

Never linked: a defining unit's own term and aliases (no self-loop; other terms in a definition
do link), and text inside reference mentions, so the "Pemerintah" of "Peraturan Pemerintah" is
not a use of the defined "Pemerintah".

Data categories: the classification Pasal (Pasal 4 in UU 27/2022) has an ayat "<x> terdiri
atas:" whose huruf are the classes; each later ayat starting with a class label lists that
class's members. Codes are derived from the labels and stay `proposed` until the owner confirms
them in the review list.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from common import ids
from pdp_ingest.refs import Mention
from pdp_ingest.segment import Unit

_DEFINITION = re.compile(
    r"(?P<term>.+?)(?: yang selanjutnya (?:disebut|disingkat) (?P<alias>.+?))? adalah \S",
    re.DOTALL,
)
_INTRO = "yang dimaksud dengan:"
_CLASSES = "terdiri atas:"
_TRAILER = re.compile(r"[;.,]?\s*(?:dan/atau|dan|atau)?\s*$")
_CODE_LEAD = {"data", "pribadi", "yang", "bersifat", "dan", "informasi"}
_OPEN = " sesuai dengan "
_ENCLITIC = "(?:nya)?"
# Classification Pasal per source, for data_categories().
CLASSIFICATION_PASAL = {"uu27-2022": "p4"}
_Match = tuple[int, int, str]  # start, end, definition node id


class DefsError(Exception):
    """The definitional or classification article does not have the expected shape."""


@dataclass(frozen=True)
class Definition:
    node_id: str  # <source>/def/<slug>
    unit_id: str  # defining unit
    term: str
    aliases: tuple[str, ...]
    text: str  # the whole definition item

    @property
    def term_norm(self) -> str:
        return " ".join(self.term.lower().split())


@dataclass(frozen=True)
class TermUse:
    unit_id: str
    node_id: str
    kind: Literal["defined", "informal"]  # defined -> USES_TERM edge; informal -> no edge
    count: int
    spans: tuple[tuple[int, int], ...]  # char spans in the unit text

    @property
    def confidence(self) -> Literal["high", "low"]:
        return "high" if self.kind == "defined" else "low"


@dataclass(frozen=True)
class DataCategory:
    code: str
    label: str  # as written, list punctuation removed
    unit_id: str
    parent_code: str | None  # None for a class (SPESIFIK, UMUM)
    open: bool  # "... sesuai dengan ketentuan peraturan perundang-undangan": open-ended
    explanation: str | None  # Penjelasan text, None for "Cukup jelas."
    status: Literal["proposed", "confirmed"] = "proposed"


def _source(units: list[Unit]) -> str:
    return units[0].unit_id.split("/", 1)[0]


def extract_definitions(units: list[Unit]) -> list[Definition]:
    """The definitions of the definitional Pasal, in order."""
    if not units:
        return []
    head = next((u for u in units if u.kind == "PASAL" and u.text.endswith(_INTRO)), None)
    if head is None:
        return []
    items = [u for u in units if u.parent_id == head.unit_id and u.kind != "PENJELASAN"]
    parsed = []
    for u in items:
        m = _DEFINITION.match(u.text)
        if m is None:
            raise DefsError(f"{u.unit_id}: no '<term> adalah ...' definition")
        alias = m.group("alias")
        parsed.append((u, m.group("term").strip(), (alias.strip(),) if alias else ()))
    slugs = ids.assign_slugs(term for _, term, _ in parsed)
    source = _source(units)
    return [
        Definition(
            ids.format(ids.UnitId(source, ids.DefinitionPath(slug))),
            u.unit_id,
            term,
            aliases,
            u.text,
        )
        for (u, term, aliases), slug in zip(parsed, slugs, strict=True)
    ]


def _surface_pattern(surface: str, *, ignore_case: bool) -> re.Pattern[str]:
    words = r"\s+".join(re.escape(w) for w in surface.split())
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(rf"(?<![\w-]){words}{_ENCLITIC}(?![\w-])", flags)


def _inside(spans: Iterable[tuple[int, int]], a: int, b: int) -> bool:
    return any(s <= a and b <= e for s, e in spans)


def _overlaps(spans: Iterable[tuple[int, int]], a: int, b: int) -> bool:
    return any(a < e and s < b for s, e in spans)


def _longest_first(candidates: list[_Match], blocked: list[tuple[int, int]]) -> list[_Match]:
    """Longest candidates first; each taken unless it overlaps a blocked or taken span."""
    taken: list[_Match] = []
    for a, b, node in sorted(candidates, key=lambda c: (c[0] - c[1], c[0])):
        if not _overlaps(blocked, a, b) and not _overlaps([(s, e) for s, e, _ in taken], a, b):
            taken.append((a, b, node))
    return taken


def _matches(text: str, surfaces: list[tuple[str, str]], *, ignore_case: bool) -> list[_Match]:
    return [
        (m.start(), m.end(), node)
        for surface, node in surfaces
        for m in _surface_pattern(surface, ignore_case=ignore_case).finditer(text)
    ]


def _unit_uses(
    unit: Unit, surfaces: list[tuple[str, str]], blocked: list[tuple[int, int]], own: set[str]
) -> list[TermUse]:
    exact = _matches(unit.text, surfaces, ignore_case=False)
    found = _longest_first(exact, blocked)
    consumed = [(a, b) for a, b, _ in found] + blocked
    exact_spans = {(a, b) for a, b, _ in exact}
    loose = [
        c
        for c in _matches(unit.text, surfaces, ignore_case=True)
        if (c[0], c[1]) not in exact_spans and not _inside(consumed, c[0], c[1])
    ]
    informal = _longest_first(loose, blocked)
    out = []
    for kind, matches in (("defined", found), ("informal", informal)):
        by_node: dict[str, list[tuple[int, int]]] = {}
        for a, b, node in sorted(matches):
            if node not in own:
                by_node.setdefault(node, []).append((a, b))
        out += [
            TermUse(unit.unit_id, node, kind, len(spans), tuple(spans))  # type: ignore[arg-type]
            for node, spans in by_node.items()
        ]
    return out


def link_terms(units: list[Unit], defs: list[Definition], mentions: list[Mention]) -> list[TermUse]:
    """Defined and informal term uses per unit, in unit order (defined first per unit)."""
    surfaces = [(s, d.node_id) for d in defs for s in (d.term, *d.aliases)]
    defining = {d.unit_id: d.node_id for d in defs}
    spans: dict[str, list[tuple[int, int]]] = {}
    for m in mentions:
        spans.setdefault(m.unit_id, []).append((m.start, m.end))
    return [
        use
        for u in units
        for use in _unit_uses(
            u,
            surfaces,
            spans.get(u.unit_id, []),
            {defining[u.unit_id]} if u.unit_id in defining else set(),
        )
    ]


def term_list(defs: list[Definition]) -> list[str]:
    """Terms and aliases, sorted: the protected-terms list for the index (M1.6)."""
    return sorted({s for d in defs for s in (d.term, *d.aliases)})


def _strip(text: str) -> str:
    return _TRAILER.sub("", text.strip())


def _code(label: str) -> tuple[str, bool]:
    head, sep, _ = label.partition(_OPEN)
    words = head.split()
    while words and words[0].lower() in _CODE_LEAD:
        words = words[1:]
    return "_".join(re.sub(r"[^0-9A-Z]+", "_", w.upper()).strip("_") for w in words), bool(sep)


def data_categories(units: list[Unit], *, pasal: str) -> list[DataCategory]:
    """Candidate DataCategory vocabulary from the classification Pasal, classes first."""
    source = _source(units)
    root = f"{source}/{pasal}"
    by_id = {u.unit_id: u for u in units}
    ayat = [u for u in units if u.parent_id == root and u.kind == "AYAT"]
    head = next((u for u in ayat if u.text.endswith(_CLASSES)), None)
    if head is None:
        raise DefsError(f"{root}: no ayat ending in {_CLASSES!r}")

    def children(parent: Unit) -> list[Unit]:
        return [u for u in units if u.parent_id == parent.unit_id and u.kind != "PENJELASAN"]

    def explanation(unit_id: str) -> str | None:
        pj = by_id.get(f"{unit_id}#pj")
        return None if pj is None or pj.text.startswith("Cukup jelas") else pj.text

    def make(u: Unit, parent: str | None) -> DataCategory:
        label = _strip(u.text)
        code, is_open = _code(label)
        return DataCategory(code, label, u.unit_id, parent, is_open, explanation(u.unit_id))

    classes = [make(u, None) for u in children(head)]
    out = list(classes)
    for a in ayat:
        cls = next((c for c in classes if a.text.startswith(c.label)), None)
        if a is not head and cls is not None:
            out += [make(u, cls.code) for u in children(a)]
    return out
