# SPDX-License-Identifier: Apache-2.0
"""Shared integration fixtures (need `make up`)."""

import json
import os
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from neo4j import Driver
from neo4j.exceptions import ServiceUnavailable
from sqlalchemy import Engine, create_engine, text

from common.db import PostgresSettings
from pdp_core.graph import Neo4jSettings, connect
from pdp_core.search import SearchSettings

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


# OpenSearch (M1.6): tests share the dev instance but only ever write `itest-` names.
ITEST = "itest-"
_READ_ONLY = ("_search", "_analyze", "_mapping", "_alias", "_cat", "_stats")


class GuardError(Exception):
    """A test tried to create, change or delete an index or alias outside `itest-`."""


def _check(names: list[str], what: str) -> None:
    bad = [n for n in names if not n.startswith(ITEST)]
    if bad:
        raise GuardError(f"refusing {what} on {bad}: integration tests write only {ITEST}*")


def _guard(request: httpx.Request) -> None:
    if request.method in ("GET", "HEAD"):
        return
    parts = request.url.path.strip("/").split("/")
    first = parts[0]
    if request.method == "POST" and first == "_aliases":
        for action in json.loads(request.content)["actions"]:
            for spec in action.values():
                names = [spec.get("index"), spec.get("alias")]
                names += spec.get("indices", []) + spec.get("aliases", [])
                _check([n for n in names if n], "alias change")
    elif request.method == "POST" and first == "_bulk":
        lines = request.content.decode().splitlines()[::2]
        _check([next(iter(json.loads(x).values()))["_index"] for x in lines], "bulk write")
    elif request.method == "POST" and (first in _READ_ONLY or parts[-1] in _READ_ONLY):
        return  # read-only: /_analyze, /<index>/_search, /<index>/_analyze
    else:
        _check(first.split(","), f"{request.method} /{first}")


def _delete_itest(client: httpx.Client) -> None:
    r = client.get(f"/_cat/indices/{ITEST}*", params={"format": "json", "h": "index"})
    names = [i["index"] for i in r.json()] if r.status_code == 200 else []
    for name in names:
        client.delete(f"/{name}").raise_for_status()


@pytest.fixture(scope="session")
def opensearch() -> Iterator[httpx.Client]:
    """The dev OpenSearch behind a guard that refuses writes outside `itest-*`; leftover
    `itest-*` indices are deleted at session start and end."""
    hooks = {"request": [_guard]}
    with httpx.Client(
        base_url=SearchSettings().opensearch_url, timeout=30, event_hooks=hooks
    ) as client:
        try:
            client.get("/").raise_for_status()
        except httpx.HTTPError:
            pytest.fail("OpenSearch is not reachable; run `make up`")
        _delete_itest(client)
        yield client
        _delete_itest(client)


@pytest.fixture
def itest_prefix(opensearch: httpx.Client) -> Iterator[str]:
    prefix = f"{ITEST}{uuid.uuid4().hex[:8]}-"
    yield prefix
    r = opensearch.get(f"/_cat/indices/{prefix}*", params={"format": "json", "h": "index"})
    for i in r.json() if r.status_code == 200 else []:
        opensearch.delete(f"/{i['index']}")


@pytest.fixture
def delete_itest(opensearch: httpx.Client) -> Callable[[], None]:
    return lambda: _delete_itest(opensearch)
