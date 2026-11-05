# SPDX-License-Identifier: Apache-2.0
"""Cross-check segmented units against the reference PDF's text layer (M1.2).

The primary text (Komdigi HTML) is a transcription, so every unit is compared with the salinan
PDF's OCR text. A unit's coverage is the share of its word trigrams (unigrams for units under three
words) that also occur in the matching part of the PDF: the batang tubuh is compared with the pages
before the Penjelasan, Penjelasan units with the pages from the Penjelasan onwards. The comparison
ignores word order across the part, so it finds wording differences, not misplaced text.

Units below the threshold go on a manual-review list together with the words that have no
match. Either side can be wrong (the PDF layer is OCR, too), so the owner settles each one against
the page images. An error shared by both texts is not detected.
"""

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from pypdf import PdfReader

from pdp_ingest.segment import Unit

THRESHOLD = 0.9
_WORD = re.compile(r"[a-z0-9]+")
_PAGE_HEADER = re.compile(r"(I|SALINAN|PRES\S*DEN|\S*LIK IN\S*SIA|-\s*\d+\s*-)")
_NOISE = re.compile(r"SK No .*|.*\.\s?\.\s?\.\s*")  # page stamp; catchword at page end
_PJ_START = re.compile(r"PENJE\S{1,3}ASAN")


@dataclass(frozen=True)
class Diff:
    html: str  # words in the unit (Komdigi page)
    pdf: str  # aligned words in the PDF text layer
    context: str
    suspect: str  # "html" | "pdf" | "unclear": which side probably carries the error (heuristic)


@dataclass(frozen=True)
class Finding:
    unit_id: str
    label: str
    coverage: float
    unmatched: list[str]  # unit words without a match, with context
    diffs: list[Diff] = field(default_factory=list)
    pdf_page: int | None = None  # 1-based PDF page sharing most trigrams with the unit

    @property
    def needs_review(self) -> bool:
        return self.coverage < THRESHOLD or any(d.suspect != "pdf" for d in self.diffs)


def pdf_pages(path: Path) -> list[str]:
    return [page.extract_text() or "" for page in PdfReader(path).pages]


def _clean(page: str) -> str:
    lines = page.splitlines()
    while lines and _PAGE_HEADER.fullmatch(lines[0].strip()):
        lines = lines[1:]
    return "\n".join(line for line in lines if not _NOISE.fullmatch(line.strip()))


def words(text: str) -> list[str]:
    return _WORD.findall(unicodedata.normalize("NFC", text).lower())


def _grams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


class Reference:
    """Word n-gram sets of the PDF, split into batang tubuh and Penjelasan."""

    def __init__(self, pages: list[str]) -> None:
        split = next((i for i, p in enumerate(pages) if _PJ_START.search(_clean(p)[:200])), None)
        if split is None:
            raise ValueError("no Penjelasan heading found in the reference PDF")
        self.split_page = split + 1  # 1-based
        self._parts = {
            "tubuh": words(" ".join(_clean(p) for p in pages[:split])),
            "penjelasan": words(" ".join(_clean(p) for p in pages[split:])),
        }
        self._sets = {
            (part, n): set(_grams(toks, n)) for part, toks in self._parts.items() for n in (1, 3)
        }
        self._where: dict[str, dict[tuple[str, ...], list[int]]] = {}
        for part, toks in self._parts.items():
            where = defaultdict(list)
            for i, g in enumerate(_grams(toks, 3)):
                where[g].append(i)
            self._where[part] = dict(where)
        self._pages = [set(_grams(words(_clean(p)), 3)) for p in pages]
        self.vocab: Counter[str] = Counter()  # HTML word frequencies, set by crosscheck()

    def check(self, unit: Unit) -> Finding:
        tokens = words(unit.text)
        part = "penjelasan" if unit.kind == "PENJELASAN" else "tubuh"
        if not tokens:
            return Finding(unit.unit_id, unit.label, 1.0, [])
        page = self.page(tokens, part)
        n = 3 if len(tokens) >= 3 else 1
        grams = _grams(tokens, n)
        hits = [g in self._sets[part, n] for g in grams]
        covered = [False] * len(tokens)
        for i, hit in enumerate(hits):
            if hit:
                for j in range(i, i + n):
                    covered[j] = True
        coverage = round(sum(hits) / len(hits), 3)
        diffs = self._diffs(tokens, part) if coverage < 1.0 else []
        return Finding(unit.unit_id, unit.label, coverage, _spans(tokens, covered), diffs, page)

    def page(self, tokens: list[str], part: str) -> int | None:
        """Page of the matching part sharing most trigrams with the tokens (where it starts,
        for a unit spanning pages); None without any shared trigram."""
        grams = set(_grams(tokens, 3))
        span = (
            range(self.split_page - 1)
            if part == "tubuh"
            else range(self.split_page - 1, len(self._pages))
        )
        best = max(span, key=lambda i: len(grams & self._pages[i]), default=None)
        return None if best is None or not grams & self._pages[best] else best + 1

    def _diffs(self, tokens: list[str], part: str) -> list[Diff]:
        """Align the unit with the PDF window around its matching trigrams; word-level diffs."""
        where = self._where[part]
        starts = sorted(  # anchor on trigrams that occur once in the PDF part
            where[g][0] - i for i, g in enumerate(_grams(tokens, 3)) if len(where.get(g, ())) == 1
        )
        if not starts:
            return []
        anchor = starts[len(starts) // 2]  # median start position of the unit in the PDF
        pdf = self._parts[part]
        lo, hi = max(0, anchor - 5), min(len(pdf), anchor + len(tokens) + 5)
        window = pdf[lo:hi]
        out = []
        matcher = SequenceMatcher(a=tokens, b=window, autojunk=False)
        blocks = matcher.get_opcodes()
        for k, (tag, i1, i2, j1, j2) in enumerate(blocks):  # skip pure window margins
            if tag == "equal" or (k in (0, len(blocks) - 1) and i1 == i2):
                continue
            html, ref = " ".join(tokens[i1:i2]), " ".join(window[j1:j2])
            context = " ".join(tokens[max(0, i1 - 3) : i2 + 3])
            out.append(Diff(html, ref, context, self._suspect(tokens[i1:i2], window[j1:j2])))
        return out

    def _suspect(self, html: list[str], pdf: list[str]) -> str:
        """Which side likely carries the error: a word seen elsewhere in the law is trusted."""

        def known(ws: list[str], min_count: int) -> bool:
            return bool(ws) and all(self.vocab[w] >= min_count for w in ws)

        if not pdf:
            return "unclear"  # words only in the HTML: dropped by OCR, or inserted by the page
        if known(pdf, 1) and not known(html, 2):
            return "html"
        if known(html, 2) and not known(pdf, 1):
            return "pdf"
        return "unclear"


def _spans(tokens: list[str], covered: list[bool]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if covered[i]:
            i += 1
            continue
        j = i
        while j < len(tokens) and not covered[j]:
            j += 1
        before = " ".join(tokens[max(0, i - 3) : i])
        after = " ".join(tokens[j : j + 3])
        out.append(f"{before} [{' '.join(tokens[i:j])}] {after}".strip())
        i = j
    return out


def crosscheck(units: list[Unit], pages: list[str]) -> tuple[Reference, list[Finding]]:
    ref = Reference(pages)
    ref.vocab = Counter(w for u in units for w in words(u.text))
    return ref, [ref.check(u) for u in units]
