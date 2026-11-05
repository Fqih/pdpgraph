# SPDX-License-Identifier: Apache-2.0
"""Shared integration fixtures (need `make up`)."""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text

from common.db import PostgresSettings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def engine() -> Iterator[Engine]:
    """A fresh, empty database for each test, dropped afterwards."""
    admin_url = PostgresSettings().url()
    name = f"pdpgraph_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    eng = create_engine(admin_url.set(database=name))
    try:
        yield eng
    finally:
        eng.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def migrated(engine: Engine) -> Engine:
    """A fresh database at Alembic head."""
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["url"] = engine.url
    command.upgrade(cfg, "head")
    return engine
