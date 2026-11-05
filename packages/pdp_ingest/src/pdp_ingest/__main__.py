# SPDX-License-Identifier: Apache-2.0
"""`python -m pdp_ingest --source uu27-2022`: run the ingestion stages implemented so far."""

import argparse
from pathlib import Path

from sqlalchemy import create_engine

from common.db import PostgresSettings
from pdp_ingest.db import register_source
from pdp_ingest.fetch import fetch_source
from pdp_ingest.registry import load_source

STAGES = ("fetch",)  # extended by M1.2+


def main() -> None:
    parser = argparse.ArgumentParser(prog="pdp_ingest")
    parser.add_argument("--source", required=True)
    parser.add_argument("--registry", type=Path, default=Path("configs/sources"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    args = parser.parse_args()

    entry = load_source(args.source, args.registry)
    records = fetch_source(entry, raw_dir=args.raw_dir, processed_dir=args.processed_dir)
    for r in records:
        origin = (
            f"fetched {r['fetched_at']} from {r['url']}" if r["url"] else "local, no provenance"
        )
        print(f"{r['role']}: {r['raw_sha256']} {r['bytes']} bytes, verified ({origin})")
    engine = create_engine(PostgresSettings().url())
    try:
        register_source(engine, entry, records[0])
    finally:
        engine.dispose()
    print(f"sources row upserted: {entry.source_id} (body sha256 {entry.primary.body_sha256})")


if __name__ == "__main__":
    main()
