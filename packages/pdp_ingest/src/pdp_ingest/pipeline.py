# SPDX-License-Identifier: Apache-2.0
"""Text stages after `fetch` (03 §5.1, M1.2-M1.3): extract -> segment -> overrides -> refs,
plus the PDF cross-check.

Artifacts under `data/processed/<source_id>/`:

- `extract.jsonl`: the canonical body blocks in order (`i`, `path`, `list_item_start`, `text`);
- `segment.jsonl`: structures and units as segmented, before overrides;
- `units.jsonl`: the units with `data/overrides/<source_id>.yaml` applied (input of later stages);
- `refs.jsonl`: reference and delegation mentions with resolved targets (`refs.py`);
- `crosscheck.jsonl`: one finding per unit against the reference PDF.

The owner's review lists go to `data/review/<source_id>/`: `crosscheck.md` (`review.py`) and
`refs.md` (`refs_review.py`).
"""

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pdp_ingest.canonical import Block, blocks
from pdp_ingest.crosscheck import Finding, crosscheck, pdf_pages
from pdp_ingest.fetch import element_inner_html, load_verified
from pdp_ingest.overrides import Override, apply_overrides, load_overrides
from pdp_ingest.refs import Mention, extract_refs
from pdp_ingest.registry import SourceEntry
from pdp_ingest.segment import Segmented, Unit, segment


@dataclass(frozen=True)
class TextResult:
    extracted: list[Block]
    segmented: Segmented
    overrides: list[Override]
    units: list[Unit]  # overrides applied
    findings: list[Finding]
    split_page: int  # first PDF page of the Penjelasan
    mentions: list[Mention] = field(default_factory=list)


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    tmp.replace(path)


def read_units(path: Path) -> list[Unit]:
    return [Unit(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines()]


def segment_source(
    entry: SourceEntry, *, raw_dir: Path, overrides_dir: Path
) -> tuple[list[Block], Segmented, list[Override], list[Unit]]:
    """extract -> segment -> overrides on the verified primary text (no cross-check)."""
    html_path, _ = load_verified(entry, raw_dir)
    body = element_inner_html(html_path.read_text(encoding="utf-8"), entry.primary.body_element_id)
    extracted = blocks(body)
    marker = entry.primary.invariants.explanation_marker
    segmented = segment(entry.source_id, extracted, explanation_marker=marker)
    overrides = load_overrides(overrides_dir / f"{entry.source_id}.yaml")
    return extracted, segmented, overrides, apply_overrides(segmented.units, overrides)


def run_text_stages(
    entry: SourceEntry, *, raw_dir: Path, overrides_dir: Path, processed_dir: Path | None = None
) -> TextResult:
    """Run the stages on the verified raw files; write artifacts when `processed_dir` is set."""
    extracted, segmented, overrides, units = segment_source(
        entry, raw_dir=raw_dir, overrides_dir=overrides_dir
    )
    _, pdf_path = load_verified(entry, raw_dir)
    ref, findings = crosscheck(units, pdf_pages(pdf_path))
    mentions = extract_refs(units)
    result = TextResult(extracted, segmented, overrides, units, findings, ref.split_page, mentions)
    if processed_dir is not None:
        out = processed_dir / entry.source_id
        _write_jsonl(
            out / "extract.jsonl",
            (
                {"i": i, "path": list(b.path), "list_item_start": b.list_item_start, "text": b.text}
                for i, b in enumerate(extracted)
            ),
        )
        _write_jsonl(
            out / "segment.jsonl",
            [{"type": "structure", **asdict(s)} for s in segmented.structures]
            + [{"type": "unit", **asdict(u)} for u in segmented.units],
        )
        _write_jsonl(out / "units.jsonl", (asdict(u) for u in units))
        _write_jsonl(out / "refs.jsonl", (asdict(m) for m in mentions))
        _write_jsonl(out / "crosscheck.jsonl", (asdict(f) for f in findings))
    return result
