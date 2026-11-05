# SPDX-License-Identifier: Apache-2.0
"""`python -m pdp_ingest --source uu27-2022`: run the ingestion stages implemented so far."""

import argparse
from pathlib import Path

from sqlalchemy import create_engine

from common.db import PostgresSettings
from pdp_ingest.db import register_source
from pdp_ingest.defs_review import defs_markdown, read_defs_reviews
from pdp_ingest.fetch import fetch_source
from pdp_ingest.overrides import counts
from pdp_ingest.pipeline import run_text_stages
from pdp_ingest.refs_review import refs_markdown
from pdp_ingest.registry import load_source
from pdp_ingest.review import read_reviews, review_markdown

STAGES = (
    "fetch",
    "extract",
    "segment",
    "overrides",
    "refs",
    "defs",
    "crosscheck",
)  # extended by M1.5+


def main() -> None:
    parser = argparse.ArgumentParser(prog="pdp_ingest")
    parser.add_argument("--source", required=True)
    parser.add_argument("--registry", type=Path, default=Path("configs/sources"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--overrides-dir", type=Path, default=Path("data/overrides"))
    parser.add_argument("--review-dir", type=Path, default=Path("data/review"))
    args = parser.parse_args()

    entry = load_source(args.source, args.registry)
    records = fetch_source(entry, raw_dir=args.raw_dir, processed_dir=args.processed_dir)
    for r in records:
        origin = (
            f"fetched {r['fetched_at']} from {r['url']}" if r["url"] else "local, no provenance"
        )
        print(f"{r['role']}: {r['raw_sha256']} {r['bytes']} bytes, verified ({origin})")

    result = run_text_stages(
        entry,
        raw_dir=args.raw_dir,
        overrides_dir=args.overrides_dir,
        processed_dir=args.processed_dir,
    )
    kinds = sorted({u.kind for u in result.units})
    by_kind = ", ".join(f"{k} {sum(u.kind == k for u in result.units)}" for k in kinds)
    print(f"extract: {len(result.extracted)} blocks")
    print(f"segment: {len(result.segmented.structures)} structures; units {by_kind}")
    total, unconfirmed = counts(result.overrides)
    print(f"overrides: {total} total, {unconfirmed} unconfirmed")
    review = args.review_dir / entry.source_id / "crosscheck.md"
    reviews = read_reviews(review.read_text(encoding="utf-8")) if review.is_file() else {}
    review.parent.mkdir(parents=True, exist_ok=True)
    review.write_text(review_markdown(entry, result, reviews), encoding="utf-8")
    flagged = sum(f.needs_review for f in result.findings)
    print(f"crosscheck: {flagged} of {len(result.findings)} units flagged, list in {review}")
    refs_list = review.parent / "refs.md"
    refs_list.write_text(
        refs_markdown(entry.source_id, result.mentions, result.units), encoding="utf-8"
    )
    unresolved = sum(m.resolution == "UNRESOLVED" for m in result.mentions)
    print(f"refs: {len(result.mentions)} mentions, {unresolved} unresolved, list in {refs_list}")
    defs_list = review.parent / "definitions.md"
    defs_reviews = (
        read_defs_reviews(defs_list.read_text(encoding="utf-8")) if defs_list.is_file() else {}
    )
    defs_list.write_text(
        defs_markdown(
            entry.source_id,
            result.definitions,
            result.term_uses,
            result.categories,
            result.units,
            defs_reviews,
            {f.unit_id: f.pdf_page for f in result.findings},
        ),
        encoding="utf-8",
    )
    edges = sum(u.kind == "defined" for u in result.term_uses)
    print(
        f"defs: {len(result.definitions)} definitions, {edges} USES_TERM links, "
        f"{len(result.term_uses) - edges} informal, {len(result.categories)} data categories, "
        f"list in {defs_list}"
    )

    engine = create_engine(PostgresSettings().url())
    try:
        register_source(engine, entry, records[0], counts(result.overrides))
    finally:
        engine.dispose()
    print(
        f"sources row upserted: {entry.source_id} (body sha256 {entry.primary.body_sha256}, "
        f"overrides {total}/{unconfirmed} unconfirmed)"
    )


if __name__ == "__main__":
    main()
