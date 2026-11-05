# SPDX-License-Identifier: Apache-2.0
"""Unit and node identifiers per 04-data-model §2 (FR-PDP-02).

`parse` and `format` implement the normative grammar in 04 §2.1 exactly; inputs are never
case-folded, and malformed IDs raise `InvalidIdError`. `parse(format(x)) == x` holds for every
valid object (property-tested).
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from common.errors import InvalidIdError

_INT = r"[1-9][0-9]*"
_SOURCE_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]*")
_LETTER_RE = re.compile(r"[a-z]")
_LETTERS_RE = re.compile(r"[a-z]+")

_ID_RE = re.compile(
    rf"(?P<src>{_SOURCE_RE.pattern})/"
    r"(?:"
    rf"bab(?P<bab>{_INT})(?:/bag(?P<bag>{_INT})(?:/par(?P<par>{_INT}))?)?"
    rf"|p(?P<p>{_INT})(?P<ps>[a-z])?(?:/a(?P<a>{_INT})(?P<as>[a-z])?)?"
    rf"(?:/h(?P<h>[a-z]+))?(?:/n(?P<n>{_INT}))?"
    rf"|def/(?P<slug>{_SLUG_RE.pattern})"
    rf"|obl/p(?P<op>{_INT})(?P<ops>[a-z])?-(?P<seq>[0-9]{{2}})"
    r"|(?P<pju>pj-umum)"
    r")"
    r"(?P<pj>#pj)?"
    rf"(?:@(?P<ver>{_INT}))?"
)


def _positive(value: int | None, what: str) -> None:
    if value is not None and value < 1:
        raise InvalidIdError(f"{what} must be >= 1, got {value}")


def _matches(pattern: re.Pattern[str], value: str | None, what: str) -> None:
    if value is not None and not pattern.fullmatch(value):
        raise InvalidIdError(f"invalid {what}: {value!r}")


@dataclass(frozen=True, slots=True)
class Structure:
    """BAB / Bagian / Paragraf grouping unit (not citable)."""

    bab: int
    bagian: int | None = None
    paragraf: int | None = None

    def __post_init__(self) -> None:
        _positive(self.bab, "bab")
        _positive(self.bagian, "bagian")
        _positive(self.paragraf, "paragraf")
        if self.paragraf is not None and self.bagian is None:
            raise InvalidIdError("paragraf requires bagian")


@dataclass(frozen=True, slots=True)
class PasalPath:
    """Pasal, optionally narrowed to ayat, huruf, and angka."""

    pasal: int
    pasal_suffix: str | None = None
    ayat: int | None = None
    ayat_suffix: str | None = None
    huruf: str | None = None
    angka: int | None = None

    def __post_init__(self) -> None:
        for value, what in ((self.pasal, "pasal"), (self.ayat, "ayat"), (self.angka, "angka")):
            _positive(value, what)
        _matches(_LETTER_RE, self.pasal_suffix, "pasal suffix")
        _matches(_LETTER_RE, self.ayat_suffix, "ayat suffix")
        _matches(_LETTERS_RE, self.huruf, "huruf")
        if self.ayat_suffix is not None and self.ayat is None:
            raise InvalidIdError("ayat suffix requires ayat")


@dataclass(frozen=True, slots=True)
class DefinitionPath:
    slug: str

    def __post_init__(self) -> None:
        _matches(_SLUG_RE, self.slug, "definition slug")


@dataclass(frozen=True, slots=True)
class ObligationPath:
    pasal: int
    seq: int
    pasal_suffix: str | None = None

    def __post_init__(self) -> None:
        _positive(self.pasal, "pasal")
        _matches(_LETTER_RE, self.pasal_suffix, "pasal suffix")
        if not 1 <= self.seq <= 99:
            raise InvalidIdError(f"obligation seq must be 1..99, got {self.seq}")


@dataclass(frozen=True, slots=True)
class PjUmum:
    """Penjelasan Umum (general elucidation)."""


Path = Structure | PasalPath | DefinitionPath | ObligationPath | PjUmum


@dataclass(frozen=True, slots=True)
class UnitId:
    """A legal or structural unit, independent of version."""

    source_id: str
    path: Path
    penjelasan: bool = False

    def __post_init__(self) -> None:
        _matches(_SOURCE_RE, self.source_id, "source_id")


@dataclass(frozen=True, slots=True)
class NodeId:
    """One version of a unit: `{unit_id}@{version}`."""

    unit: UnitId
    version: int

    def __post_init__(self) -> None:
        _positive(self.version, "version")


def _opt_int(value: str | None) -> int | None:
    return int(value) if value is not None else None


def _path_from_match(m: re.Match[str]) -> Path:
    if m["bab"]:
        return Structure(int(m["bab"]), _opt_int(m["bag"]), _opt_int(m["par"]))
    if m["p"]:
        return PasalPath(
            pasal=int(m["p"]),
            pasal_suffix=m["ps"],
            ayat=_opt_int(m["a"]),
            ayat_suffix=m["as"],
            huruf=m["h"],
            angka=_opt_int(m["n"]),
        )
    if m["slug"]:
        return DefinitionPath(m["slug"])
    if m["op"]:
        return ObligationPath(pasal=int(m["op"]), seq=int(m["seq"]), pasal_suffix=m["ops"])
    return PjUmum()


def parse(text: str) -> NodeId | UnitId:
    """Parse a `unit_id` or `node_id`; raise `InvalidIdError` if it is not grammatical."""
    m = _ID_RE.fullmatch(text)
    if m is None:
        raise InvalidIdError(f"not a valid unit or node id: {text!r}")
    unit = UnitId(m["src"], _path_from_match(m), penjelasan=m["pj"] is not None)
    return NodeId(unit, int(m["ver"])) if m["ver"] else unit


def _format_path(path: Path) -> str:
    match path:
        case Structure(bab, bagian, paragraf):
            out = f"bab{bab}"
            if bagian is not None:
                out += f"/bag{bagian}"
            if paragraf is not None:
                out += f"/par{paragraf}"
            return out
        case PasalPath(pasal, pasal_suffix, ayat, ayat_suffix, huruf, angka):
            out = f"p{pasal}{pasal_suffix or ''}"
            if ayat is not None:
                out += f"/a{ayat}{ayat_suffix or ''}"
            if huruf is not None:
                out += f"/h{huruf}"
            if angka is not None:
                out += f"/n{angka}"
            return out
        case DefinitionPath(slug):
            return f"def/{slug}"
        case ObligationPath(pasal, seq, pasal_suffix):
            return f"obl/p{pasal}{pasal_suffix or ''}-{seq:02d}"
        case PjUmum():
            return "pj-umum"


def format(obj: NodeId | UnitId) -> str:
    """Render an ID object as its canonical string."""
    if isinstance(obj, NodeId):
        return f"{format(obj.unit)}@{obj.version}"
    return f"{obj.source_id}/{_format_path(obj.path)}{'#pj' if obj.penjelasan else ''}"


def slugify(term: str) -> str:
    """Definition slug: NFKD ASCII fold, lowercase, non-alphanumerics to '-', collapse/trim."""
    folded = unicodedata.normalize("NFKD", term).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    if not slug:
        raise InvalidIdError(f"term has no letters or digits to slugify: {term!r}")
    return slug


def assign_slugs(terms: Iterable[str]) -> list[str]:
    """Slugs for terms in order of appearance; collisions get -2, -3, ... (04 §2.1)."""
    used: set[str] = set()
    out: list[str] = []
    for term in terms:
        base = slug = slugify(term)
        n = 1
        while slug in used:
            n += 1
            slug = f"{base}-{n}"
        used.add(slug)
        out.append(slug)
    return out
