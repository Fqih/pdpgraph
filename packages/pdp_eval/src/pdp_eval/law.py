# SPDX-License-Identifier: Apache-2.0
"""Law text view for the labeling CLI (M1.7): Pasal lines with their unit ids.

Built from the segmented units (`pdp_ingest.pipeline.segment_source`, overrides applied), so the
ids the annotator types are the ids the pipeline produces.
"""

from dataclasses import dataclass
from pathlib import Path

from common import ids
from pdp_ingest.pipeline import segment_source
from pdp_ingest.registry import load_source
from pdp_ingest.segment import Unit


@dataclass(frozen=True)
class Line:
    unit_id: str | None  # None for a Pasal's own text before its list
    label: str
    text: str
    depth: int = 0


def _short_label(unit: Unit) -> str:
    """The list marker of a unit from its label ("... ayat (1)" -> "(1)", "... huruf b" -> "b.")."""
    marker = unit.label.rsplit(" ", 1)[-1]
    return marker if unit.kind == "AYAT" else f"{marker}."


class LawText:
    def __init__(self, source_id: str, units: list[Unit]) -> None:
        self.source_id = source_id
        self._units = {u.unit_id: u for u in units}
        self._pasal: dict[int, list[Unit]] = {}
        self._pj: dict[int, list[Unit]] = {}
        for u in units:
            parsed = ids.parse(u.unit_id)
            if isinstance(parsed, ids.UnitId) and isinstance(parsed.path, ids.PasalPath):
                path = parsed.path
                group = self._pj if u.kind == "PENJELASAN" else self._pasal
                group.setdefault(path.pasal, []).append(u)

    @classmethod
    def from_source(
        cls, source_id: str, registry_dir: Path, raw_dir: Path, overrides_dir: Path
    ) -> "LawText":
        entry = load_source(source_id, registry_dir)
        *_, units = segment_source(entry, raw_dir=raw_dir, overrides_dir=overrides_dir)
        return cls(source_id, units)

    def pasal(self, n: int) -> list[Line]:
        if n not in self._pasal:
            raise KeyError(f"Pasal {n} not in {self.source_id}")
        head, *children = self._pasal[n]
        lines = [Line(head.unit_id, head.label, "")]
        if head.text:
            lines.append(Line(None, "", head.text))
        lines += [Line(u.unit_id, _short_label(u), u.text, u.depth) for u in children]
        return lines

    def explanation(self, n: int) -> list[str]:
        """Penjelasan of Pasal n, each part prefixed with the explained sub-unit."""
        out = []
        for u in self._pj.get(n, []):
            where = u.label.removeprefix(f"Penjelasan Pasal {n}").strip()
            out.append(f"{where}: {u.text}" if where else u.text)
        return out

    def general_explanation(self) -> list[str]:
        umum = self._units.get(f"{self.source_id}/pj-umum")
        return umum.text.split("\n") if umum else []

    def has_unit(self, unit_id: str) -> bool:
        return unit_id in self._units
