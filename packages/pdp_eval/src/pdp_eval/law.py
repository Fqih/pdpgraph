# SPDX-License-Identifier: Apache-2.0
"""Law text view for the labeling CLI (M1.7): Pasal lines with suggested unit ids.

Built from the verified source snapshot (pdp_ingest canonical blocks) so labeling can start
before segmentation lands. Ayat/huruf/angka are inferred from list nesting with the drafting
convention (UU 12/2011): a Pasal whose list follows intro text lists huruf (angka for the
definitions in "yang dimaksud dengan:"); otherwise the first level is ayat. Once M1.3 ships the
segmented units, the CLI should read ids from there instead.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from pdp_ingest.canonical import Block, blocks
from pdp_ingest.fetch import element_inner_html, load_verified
from pdp_ingest.registry import load_source

_PASAL = re.compile(r"Pasal (\d+)")
_STOP = re.compile(r"Pasal \d+|BAB [IVXLC]+|Bagian \w+|Paragraf \d+|Agar setiap orang .*")


@dataclass(frozen=True)
class Line:
    unit_id: str | None  # None for intro text and continuation blocks
    label: str
    text: str
    depth: int = 0


def _segment(kind: str, index: int) -> tuple[str, str]:
    if kind == "a":
        return f"/a{index}", f"({index})"
    if kind == "h":
        if index > 26:
            raise ValueError(f"huruf index {index} out of range")
        letter = chr(ord("a") + index - 1)
        return f"/h{letter}", f"{letter}."
    return f"/n{index}", f"{index}."


class LawText:
    def __init__(self, source_id: str, body: list[Block], *, explanation_marker: str) -> None:
        split = next(i for i, b in enumerate(body) if not b.path and b.text == explanation_marker)
        self.source_id = source_id
        self._tubuh = self._by_pasal(body[:split])
        self._penjelasan = self._by_pasal(body[split + 1 :])
        self._umum = self._before_first_pasal(body[split + 1 :])
        self._ids = {
            line.unit_id for n in self._tubuh for line in self.pasal(n) if line.unit_id
        } | {f"{source_id}/pj-umum"}

    @classmethod
    def from_source(cls, source_id: str, registry_dir: Path, raw_dir: Path) -> "LawText":
        entry = load_source(source_id, registry_dir)
        html_path, _ = load_verified(entry, raw_dir)
        page = html_path.read_text(encoding="utf-8")
        body = blocks(element_inner_html(page, entry.primary.body_element_id))
        return cls(source_id, body, explanation_marker=entry.primary.invariants.explanation_marker)

    @staticmethod
    def _by_pasal(part: list[Block]) -> dict[int, list[Block]]:
        out: dict[int, list[Block]] = {}
        current: list[Block] | None = None
        for b in part:
            if not b.path and _STOP.fullmatch(b.text):
                m = _PASAL.fullmatch(b.text)
                current = out.setdefault(int(m.group(1)), []) if m else None
            elif current is not None:
                current.append(b)
        return out

    @staticmethod
    def _before_first_pasal(part: list[Block]) -> list[str]:
        out = []
        for b in part:
            if not b.path and _PASAL.fullmatch(b.text):
                break
            out.append(b.text)
        return out

    def pasal(self, n: int) -> list[Line]:
        if n not in self._tubuh:
            raise KeyError(f"Pasal {n} not in {self.source_id}")
        base = f"{self.source_id}/p{n}"
        lines = [Line(base, f"Pasal {n}", "")]
        intro = [b for b in self._tubuh[n] if not b.path]
        if not intro:
            kinds = "ahn"
        elif intro[0].text.endswith("yang dimaksud dengan:"):
            kinds = "nnn"
        else:
            kinds = "hnn"
        for b in self._tubuh[n]:
            if not b.list_item_start:
                lines.append(Line(None, "", b.text, len(b.path)))
                continue
            segments = [_segment(kinds[d], i) for d, i in enumerate(b.path)]
            unit_id = base + "".join(s for s, _ in segments)
            lines.append(Line(unit_id, segments[-1][1], b.text, len(b.path)))
        return lines

    def explanation(self, n: int) -> list[str]:
        return [b.text for b in self._penjelasan.get(n, [])]

    def general_explanation(self) -> list[str]:
        return list(self._umum)

    def has_unit(self, unit_id: str) -> bool:
        return unit_id.removesuffix("#pj") in self._ids
