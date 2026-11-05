# SPDX-License-Identifier: Apache-2.0
"""Canonical form of a law body and its content invariants (M1.1, SEC-14).

Canonicalization v1 (`html-element-blocks`), applied to the inner HTML of the body element:

1. Parse with the stdlib HTML parser (character references decoded).
2. Block tags (p, div, li, br, h1-h6, table cells, ...) end the current text block; inline tags
   (span, strong, a, ...) are transparent. Attributes are ignored.
3. Each block: Unicode NFC, every whitespace run (incl. NBSP) collapsed to one space, stripped;
   empty blocks dropped.
4. Lists are kept because ayat/huruf numbering is implicit in `<ol>` nesting: `[ol]`/`[ul]` and
   `[/ol]`/`[/ul]` lines, and the first block of each `<li>` is prefixed `[li] `.
5. Lines joined with "\\n", UTF-8, SHA-256.

Any change to these rules is a new version; bump CANONICALIZATION_VERSION and re-pin.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser

from pydantic import BaseModel, ConfigDict, Field

CANONICALIZATION_VERSION = 1
EXTRACTION_METHOD = "html-element-blocks"

_LISTS = {"ol", "ul"}
_BLOCKS = {
    "address", "article", "blockquote", "br", "dd", "div", "dl", "dt", "figure", "footer",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "p", "pre", "section", "table",
    "tbody", "td", "tfoot", "th", "thead", "tr",
} | _LISTS  # fmt: skip
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class Block:
    text: str
    path: tuple[int, ...]  # 1-based item index at each list depth; () outside lists
    list_item_start: bool = False


class _Walker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.blocks: list[Block] = []
        self._buf: list[str] = []
        self._counters: list[int] = []  # item count per open list
        self._item_open = False

    def _flush(self) -> None:
        text = _WS.sub(" ", unicodedata.normalize("NFC", "".join(self._buf))).strip()
        self._buf = []
        if not text:
            return
        block = Block(text, tuple(self._counters), self._item_open)
        self.lines.append(f"[li] {text}" if self._item_open else text)
        self.blocks.append(block)
        self._item_open = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in _BLOCKS:
            return
        self._flush()
        if tag in _LISTS:
            self.lines.append(f"[{tag}]")
            self._counters.append(0)
        elif tag == "li" and self._counters:
            self._counters[-1] += 1
            self._item_open = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCKS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag not in _BLOCKS:
            return
        self._flush()
        if tag in _LISTS and self._counters:
            self._counters.pop()
            self.lines.append(f"[/{tag}]")

    def handle_data(self, data: str) -> None:
        self._buf.append(data)


def _walk(html: str) -> _Walker:
    walker = _Walker()
    walker.feed(html)
    walker.close()
    walker._flush()
    return walker


def blocks(html: str) -> list[Block]:
    return _walk(html).blocks


def canonical_text(html: str) -> str:
    return "\n".join(_walk(html).lines)


def canonical_sha256(html: str) -> str:
    return hashlib.sha256(canonical_text(html).encode("utf-8")).hexdigest()


class InvariantError(Exception):
    """The extracted body violates a registered content invariant."""


class ItemAt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pasal: int = Field(ge=1)
    path: list[int] = Field(min_length=1)  # e.g. [3, 3] = ayat (3) huruf c
    text: str = Field(min_length=1)


class ContentInvariants(BaseModel):
    """Expected shape of the body; checked on every fetch before the hash (registry-driven)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    starts_with: list[str] = Field(min_length=1)  # first block texts
    ends_with: list[str] = Field(min_length=1)  # last block texts
    explanation_marker: str  # first top-level block equal to this starts the Penjelasan
    pasal_headings: int = Field(ge=1)  # exactly "Pasal 1".."Pasal N", in order, in both parts
    bab_headings: int = Field(ge=1)  # exactly "BAB I".."BAB N", in order, batang tubuh
    cukup_jelas: int = Field(ge=0)  # blocks reading "Cukup jelas" (final period optional)
    items: list[ItemAt] = []


_PASAL = re.compile(r"Pasal (\d+)")
_BAB = re.compile(r"BAB ([IVXLC]+)")
_CUKUP_JELAS = re.compile(r"Cukup jelas\.?")
_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def _roman(numeral: str) -> int:
    values = [_ROMAN[c] for c in numeral]
    return sum(-v if v < nxt else v for v, nxt in zip(values, [*values[1:], 0], strict=True))


def _headings(part: list[Block], pattern: re.Pattern[str]) -> list[str]:
    return [m.group(1) for b in part if not b.path and (m := pattern.fullmatch(b.text))]


def _expect_sequence(found: list[int], n: int, what: str) -> None:
    if found != list(range(1, n + 1)):
        missing = sorted(set(range(1, n + 1)) - set(found))
        raise InvariantError(
            f"{what}: expected 1..{n} in order, found {len(found)} "
            f"(missing {missing[:10]}, first {found[:5]}...)"
        )


def _item(body: list[Block], item: ItemAt) -> str:
    target, inside = f"Pasal {item.pasal}", False
    for b in body:
        if not b.path and _PASAL.fullmatch(b.text):
            if inside:
                break
            inside = b.text == target
        elif inside and b.list_item_start and list(b.path) == item.path:
            if b.text != item.text:
                raise InvariantError(f"{target} path {item.path}: {b.text!r} != {item.text!r}")
            return f"{target} path {item.path} = {b.text!r}"
    raise InvariantError(f"{target} path {item.path}: not found")


def check_invariants(body: list[Block], inv: ContentInvariants) -> dict[str, object]:
    texts = [b.text for b in body]
    if texts[: len(inv.starts_with)] != inv.starts_with:
        raise InvariantError(f"starts_with: body starts {texts[: len(inv.starts_with)]}")
    if texts[-len(inv.ends_with) :] != inv.ends_with:
        raise InvariantError(f"ends_with: body ends {texts[-len(inv.ends_with) :]}")
    split = next(
        (i for i, b in enumerate(body) if not b.path and b.text == inv.explanation_marker), None
    )
    if split is None:
        raise InvariantError(f"explanation marker {inv.explanation_marker!r} not found")
    tubuh, penjelasan = body[:split], body[split:]
    babs = [_roman(r) for r in _headings(tubuh, _BAB)]
    _expect_sequence(babs, inv.bab_headings, "BAB headings (batang tubuh)")
    for part, name in ((tubuh, "batang tubuh"), (penjelasan, "penjelasan")):
        found = [int(n) for n in _headings(part, _PASAL)]
        _expect_sequence(found, inv.pasal_headings, f"Pasal headings ({name})")
    cukup = sum(1 for t in texts if _CUKUP_JELAS.fullmatch(t))
    if cukup != inv.cukup_jelas:
        raise InvariantError(f"Cukup jelas: expected {inv.cukup_jelas}, found {cukup}")
    return {
        "starts_with": "ok",
        "ends_with": "ok",
        "bab_headings": len(babs),
        "pasal_headings_body": inv.pasal_headings,
        "pasal_headings_explanation": inv.pasal_headings,
        "cukup_jelas": cukup,
        "items": [_item(tubuh, item) for item in inv.items],
    }
