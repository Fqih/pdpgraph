# SPDX-License-Identifier: Apache-2.0
"""Shared integration fixtures (need `make up`)."""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from neo4j import Driver
from neo4j.exceptions import ServiceUnavailable
from sqlalchemy import Engine, create_engine, text

from common.db import PostgresSettings
from pdp_core.graph import Neo4jSettings, connect

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


TEST_GRAPH_URI = os.environ.get("NEO4J_TEST_URI", "bolt://127.0.0.1:7688")
DEV_GRAPH_PORT = ":7687"


@pytest.fixture(scope="session")
def graph_driver() -> Iterator[Driver]:
    """The throwaway Neo4j test instance (`make up-test`), wiped at session start and end.
    Refuses the dev graph port, so integration tests never touch a loaded dev graph."""
    if TEST_GRAPH_URI.rstrip("/").endswith(DEV_GRAPH_PORT):
        pytest.fail(f"refusing to run graph tests against the dev graph ({TEST_GRAPH_URI})")
    with connect(Neo4jSettings(uri=TEST_GRAPH_URI)) as driver:
        try:
            driver.verify_connectivity()
        except ServiceUnavailable:
            pytest.fail(f"no Neo4j test instance at {TEST_GRAPH_URI}; run `make up-test`")
        driver.execute_query("MATCH (n) DETACH DELETE n")
        yield driver
        driver.execute_query("MATCH (n) DETACH DELETE n")
