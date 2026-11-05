# SPDX-License-Identifier: Apache-2.0
"""`python -m pdp_ingest --source uu27-2022`: run the ingestion stages implemented so far."""

import argparse
from pathlib import Path

from sqlalchemy import create_engine

from common.db import PostgresSettings
from pdp_ingest.db import register_source
from pdp_ingest.fetch import fetch_source
from pdp_ingest.overrides import summary
from pdp_ingest.pipeline import review_markdown, run_text_stages
from pdp_ingest.registry import load_source

STAGES = ("fetch", "extract", "segment", "overrides", "crosscheck")  # extended by M1.3+


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
    counts = ", ".join(f"{k} {sum(u.kind == k for u in result.units)}" for k in kinds)
    print(f"extract: {len(result.extracted)} blocks")
    print(f"segment: {len(result.segmented.structures)} structures; units {counts}")
    print(f"overrides: {dict(summary(result.overrides))}")
    review = args.review_dir / entry.source_id / "crosscheck.md"
    review.parent.mkdir(parents=True, exist_ok=True)
    review.write_text(review_markdown(entry, result), encoding="utf-8")
    flagged = sum(f.needs_review for f in result.findings)
    print(f"crosscheck: {flagged} of {len(result.findings)} units flagged, list in {review}")

    engine = create_engine(PostgresSettings().url())
    try:
        register_source(engine, entry, records[0])
    finally:
        engine.dispose()
    print(f"sources row upserted: {entry.source_id} (body sha256 {entry.primary.body_sha256})")


if __name__ == "__main__":
    main()
