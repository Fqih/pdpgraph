# SPDX-License-Identifier: Apache-2.0
"""`fetch` writes the Postgres `sources` record (04 §1, M1.1). Requires `make up`."""

from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from pdp_ingest.db import register_source
from pdp_ingest.registry import load_source

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def _record(
    fetched_at: str | None, url: str | None = "https://jdih.example.go.id/x"
) -> dict[str, object]:
    return {"role": "primary", "url": url, "fetched_at": fetched_at}


def test_register_source_upserts_the_registry_row(migrated: Engine) -> None:
    entry = load_source("uu27-2022", ROOT / "configs" / "sources")
    register_source(migrated, entry, _record("2026-11-05T01:00:00+00:00"), (0, 0))
    register_source(migrated, entry, _record("2026-11-05T02:00:00+00:00"), (31, 29))
    with migrated.connect() as conn:
        rows = conn.execute(text("SELECT * FROM sources")).mappings().all()
    (row,) = rows
    assert row["source_id"] == "uu27-2022"
    assert row["instrument_type"] == "UU"
    assert (row["number"], row["year"]) == (27, 2022)
    assert str(row["promulgated_on"]) == "2022-10-17"
    assert row["sha256"] == entry.primary.body_sha256
    assert row["url"] == "https://jdih.example.go.id/x"
    assert row["fetched_at"].isoformat() == "2026-11-05T02:00:00+00:00"
    assert row["parser_version"].startswith("pdp_ingest@")
    assert (row["overrides_total"], row["overrides_unconfirmed"]) == (31, 29)


def test_local_reuse_keeps_registry_url(migrated: Engine) -> None:
    entry = load_source("uu27-2022", ROOT / "configs" / "sources")
    register_source(migrated, entry, _record(None, url=None), (0, 0))
    with migrated.connect() as conn:
        url = conn.execute(text("SELECT url FROM sources")).scalar_one()
    assert url == str(entry.primary.url)
