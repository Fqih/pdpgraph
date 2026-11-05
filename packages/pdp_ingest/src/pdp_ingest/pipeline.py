# SPDX-License-Identifier: Apache-2.0
"""Text stages after `fetch` (03 §5.1, M1.2): extract -> segment -> overrides -> crosscheck.

Artifacts under `data/processed/<source_id>/`:

- `extract.jsonl`: the canonical body blocks in order (`i`, `path`, `list_item_start`, `text`);
- `segment.jsonl`: structures and units as segmented, before overrides;
- `units.jsonl`: the units with `data/overrides/<source_id>.yaml` applied (input of later stages);
- `crosscheck.jsonl`: one finding per unit against the reference PDF.

The manual-review list goes to `data/review/<source_id>/crosscheck.md`, which is committed: it is
the owner's checklist, and its diff shows when a source or override change moves a finding.
"""

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pdp_ingest.canonical import Block, blocks
from pdp_ingest.crosscheck import THRESHOLD, Finding, crosscheck, pdf_pages
from pdp_ingest.fetch import element_inner_html, load_verified
from pdp_ingest.overrides import Override, apply_overrides, load_overrides
from pdp_ingest.registry import SourceEntry
from pdp_ingest.segment import Segmented, Unit, segment

# Units the owner checks against the PDF page images as the snapshot sample (roadmap M1.2 DoD);
# their exact text is pinned in tests/test_segment_uu27.py.
SNAPSHOT_UNITS = {
    "uu27-2022": (
        "p1/n1",
        "p53/a1/hb",
        "p5",
        "p20/a2/hc",
        "p26/a2",
        "p46/a3",
        "p57/a3",
        "p67/a1",
        "p76",
        "p57/a3#pj",
    ),
}


@dataclass(frozen=True)
class TextResult:
    extracted: list[Block]
    segmented: Segmented
    overrides: list[Override]
    units: list[Unit]  # overrides applied
    findings: list[Finding]
    split_page: int  # first PDF page of the Penjelasan


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
    result = TextResult(extracted, segmented, overrides, units, findings, ref.split_page)
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
        _write_jsonl(out / "crosscheck.jsonl", (asdict(f) for f in findings))
    return result


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " / ")


def review_markdown(entry: SourceEntry, result: TextResult) -> str:
    """The owner's checklist: overrides to confirm, snapshot units, then flagged units."""
    sid = entry.source_id
    by_id = {u.unit_id: u for u in result.units}
    findings = {f.unit_id: f for f in result.findings}
    flagged = sorted((f for f in result.findings if f.needs_review), key=lambda f: f.coverage)
    kinds: dict[str, int] = {}
    for u in result.units:
        kinds[u.kind] = kinds.get(u.kind, 0) + 1
    unconfirmed = [o for o in result.overrides if not o.confirmed_by]
    lines = [
        f"# Cross-check review: {sid}",
        "",
        "Generated by `make ingest` (`pdp_ingest.pipeline`); do not edit by hand. Primary text: "
        f"Komdigi page, body sha256 `{entry.primary.body_sha256}`. Reference: salinan PDF "
        f"`{entry.reference.sha256}` (Penjelasan from PDF page {result.split_page}). Page numbers "
        "are 1-based PDF pages.",
        "",
        f"Units: {len(result.units)} ("
        + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items()))
        + f"). Overrides: {len(result.overrides)} ({len(unconfirmed)} unconfirmed). "
        f"Flagged for review: {len(flagged)} (coverage below {THRESHOLD}, or a word difference "
        "not attributed to PDF OCR).",
        "",
        "## 1. Overrides to confirm",
        "",
        "Applied to the Komdigi text before the cross-check. Check each against the page image, "
        f"then set `confirmed_by` in `data/overrides/{sid}.yaml`.",
        "",
        "| Unit | Komdigi text | Corrected | PDF page | Reason | Confirmed |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| `{o.unit_id}` | {_cell(o.find)} | {_cell(o.replace)} | {o.pdf_page} | "
        f"{_cell(o.reason)} | {o.confirmed_by or '-'} |"
        for o in result.overrides
    ]
    lines += [
        "",
        "## 2. Snapshot units",
        "",
        "Exact text pinned in `test_segment_uu27.py` (overrides applied). Check each against the "
        "page image.",
        "",
    ]
    for suffix in SNAPSHOT_UNITS.get(sid, ()):
        unit = by_id[f"{sid}/{suffix}"]
        page = findings[unit.unit_id].pdf_page
        lines += [
            f"- [ ] `{unit.unit_id}` {unit.label}, PDF page {page}",
            "",
            "  > " + unit.text.replace("\n", "\n  > "),
            "",
        ]
    lines += [
        "## 3. Flagged units",
        "",
        "Lowest coverage first. `suspect` is a heuristic for which side carries the error: `html` "
        "(Komdigi), `pdf` (OCR), `unclear`. A PDF-side gap usually means OCR dropped or merged "
        "words. Settle each against the page image; a Komdigi error becomes an override.",
        "",
    ]
    for f in flagged:
        lines.append(f"### `{f.unit_id}` {f.label}: coverage {f.coverage}, PDF page {f.pdf_page}")
        lines.append("")
        lines.append("> " + by_id[f.unit_id].text.replace("\n", "\n> "))
        lines.append("")
        if f.diffs:
            lines += ["| Komdigi | PDF | Suspect | Context |", "|---|---|---|---|"]
            lines += [
                f"| {_cell(d.html) or '-'} | {_cell(d.pdf) or '-'} | {d.suspect} | "
                f"{_cell(d.context)} |"
                for d in f.diffs
            ]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
