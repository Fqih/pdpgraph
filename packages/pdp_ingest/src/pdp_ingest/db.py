# SPDX-License-Identifier: Apache-2.0
"""Postgres `sources` record for a fetched source (04 §1, §6)."""

from datetime import UTC, datetime
from importlib.metadata import version
from typing import Any

from sqlalchemy import Engine, text

from pdp_ingest.registry import SourceEntry

_UPSERT = text(
    """
    INSERT INTO sources (source_id, title, instrument_type, number, year, enacted_on,
                         promulgated_on, effective_from, url, sha256, fetched_at, parser_version)
    VALUES (:source_id, :title, :instrument_type, :number, :year, :enacted_on,
            :promulgated_on, :effective_from, :url, :sha256, :fetched_at, :parser_version)
    ON CONFLICT (source_id) DO UPDATE SET
      title = EXCLUDED.title, instrument_type = EXCLUDED.instrument_type,
      number = EXCLUDED.number, year = EXCLUDED.year, enacted_on = EXCLUDED.enacted_on,
      promulgated_on = EXCLUDED.promulgated_on, effective_from = EXCLUDED.effective_from,
      url = EXCLUDED.url, sha256 = EXCLUDED.sha256, fetched_at = EXCLUDED.fetched_at,
      parser_version = EXCLUDED.parser_version
    """
)


def register_source(engine: Engine, entry: SourceEntry, primary: dict[str, Any]) -> None:
    """Upsert the registry row; `sha256` is the verified law-body hash (SEC-14)."""
    fetched_at = primary.get("fetched_at")
    params = {
        "source_id": entry.source_id,
        "title": entry.title,
        "instrument_type": entry.instrument_type,
        "number": entry.number,
        "year": entry.year,
        "enacted_on": entry.enacted_on,
        "promulgated_on": entry.promulgated_on,
        "effective_from": entry.effective_from,
        "url": primary.get("url") or str(entry.primary.url),
        "sha256": entry.primary.body_sha256,
        "fetched_at": datetime.fromisoformat(fetched_at) if fetched_at else datetime.now(UTC),
        "parser_version": f"pdp_ingest@{version('pdp-ingest')}",
    }
    with engine.begin() as conn:
        conn.execute(_UPSERT, params)
