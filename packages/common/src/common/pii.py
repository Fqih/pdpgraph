# SPDX-License-Identifier: Apache-2.0
"""Deterministic Indonesian PII patterns (FR-GW-17, SEC-16).

Single source of truth for PII detection: the LLMClient cassette guard (M0.5), log redaction
(SEC-12), and the Tierline escalation scanner (M2.11) all use this module, so the patterns
cannot diverge. Matches carry kind and offsets only, never the matched text. Patterns are
[TUNE]: they favour recall, because a false positive only routes a request to the local tier.
"""

import re
from dataclasses import dataclass
from enum import StrEnum


class PiiKind(StrEnum):
    # Order is redaction priority when matches overlap.
    NIK = "NIK"
    NPWP = "NPWP"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    CARD = "CARD"


# Digit-based values must not touch a letter or digit on either side, so digit runs inside
# hex IDs, hashes, and UUIDs are not mistaken for PII. A value glued to letters
# ("NIK3171...") is therefore missed; separators (space, ':', '=') still work.
_B = r"(?<![0-9A-Za-z])"
_E = r"(?![0-9A-Za-z])"

_PATTERNS: dict[PiiKind, re.Pattern[str]] = {
    # 16-digit Nomor Induk Kependudukan, as a standalone digit run.
    PiiKind.NIK: re.compile(rf"{_B}\d{{16}}{_E}"),
    # NPWP: formatted 99.999.999.9-999.999, or a standalone 15-digit run.
    PiiKind.NPWP: re.compile(
        rf"{_B}(?:\d{{2}}\.\d{{3}}\.\d{{3}}\.\d-\d{{3}}\.\d{{3}}|\d{{15}}){_E}"
    ),
    # Indonesian mobile numbers: +62 / 62 / 0, then 8, then 8-11 digits with optional separators.
    PiiKind.PHONE: re.compile(
        rf"(?<![0-9A-Za-z+])(?:\+62[\s-]?|62[\s-]?|0)8\d(?:[\s-]?\d){{7,10}}{_E}"
    ),
    PiiKind.EMAIL: re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
    # Card-like: 13-19 digits, optional single space/dash separators; Luhn-checked below.
    PiiKind.CARD: re.compile(rf"{_B}\d(?:[ -]?\d){{12,18}}{_E}"),
}


@dataclass(frozen=True, slots=True)
class PiiMatch:
    kind: PiiKind
    start: int
    end: int


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def find_pii(text: str) -> list[PiiMatch]:
    """All PII matches, sorted by position. Overlaps between kinds are kept."""
    matches: list[PiiMatch] = []
    for kind, pattern in _PATTERNS.items():
        for m in pattern.finditer(text):
            if kind is PiiKind.CARD and not luhn_valid(re.sub(r"\D", "", m.group())):
                continue
            matches.append(PiiMatch(kind, m.start(), m.end()))
    return sorted(matches, key=lambda m: (m.start, list(PiiKind).index(m.kind)))


def contains_pii(text: str) -> bool:
    return bool(find_pii(text))


def redact_pii(text: str) -> str:
    """Replace each PII span with `[REDACTED:<KIND>]`; overlapping spans are merged."""
    out: list[str] = []
    pos = 0
    span_end = -1
    for m in find_pii(text):
        if m.start < span_end:  # overlaps the span just redacted
            span_end = max(span_end, m.end)
            pos = span_end
            continue
        out.append(text[pos : m.start])
        out.append(f"[REDACTED:{m.kind}]")
        pos = span_end = m.end
    out.append(text[pos:])
    return "".join(out)
