# SPDX-License-Identifier: Apache-2.0
"""Compose `core` profile: four stores healthy, loopback-only, Indonesian analyzer works.

M0.2, BR-16, SEC-15, NFR-08. Requires `make up`.
"""

import json
import socket
import subprocess
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.integration

COMPOSE = ["docker", "compose", "--project-directory", ".", "-f", "deploy/compose/compose.yaml"]
STORES = {"neo4j": [7474, 7687], "opensearch": [9200], "postgres": [5432], "valkey": [6379]}


@pytest.fixture(scope="module")
def services() -> dict[str, dict[str, Any]]:
    out = subprocess.run(  # noqa: S603 - fixed argv, no user input
        [*COMPOSE, "--profile", "core", "ps", "--format", "json"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    rows = [json.loads(line) for line in out.splitlines() if line.strip()]
    found = {row["Service"]: row for row in rows}
    missing = set(STORES) - set(found)
    assert not missing, f"services not running: {sorted(missing)} (run `make up` first)"
    return found


@pytest.mark.parametrize("service", sorted(STORES))
def test_m0_2_store_is_healthy(services: dict[str, dict[str, Any]], service: str) -> None:
    assert services[service]["Health"] == "healthy"


@pytest.mark.parametrize("service", sorted(STORES))
def test_sec_15_store_ports_bound_to_loopback_only(
    services: dict[str, dict[str, Any]], service: str
) -> None:
    published = [p for p in services[service]["Publishers"] if p["PublishedPort"]]
    assert sorted(p["PublishedPort"] for p in published) == sorted(STORES[service])
    assert {p["URL"] for p in published} == {"127.0.0.1"}


@pytest.mark.parametrize("port", sorted(p for ports in STORES.values() for p in ports))
def test_m0_2_store_port_reachable_on_loopback(port: int) -> None:
    with socket.create_connection(("127.0.0.1", port), timeout=3):
        pass


def _tokens(analyzer: str, text: str) -> list[str]:
    resp = httpx.post(
        "http://127.0.0.1:9200/_analyze", json={"analyzer": analyzer, "text": text}, timeout=10
    )
    resp.raise_for_status()
    return [t["token"] for t in resp.json()["tokens"]]


def test_m0_2_opensearch_indonesian_analyzer() -> None:
    text = "Pengendali Data Pribadi yang wajib memberitahukan kegagalan dan pelindungan data"
    standard = _tokens("standard", text)
    indonesian = _tokens("indonesian", text)
    assert {"yang", "dan"} <= set(standard)
    assert not {"yang", "dan"} & set(indonesian)  # Indonesian stopwords removed
    assert "memberitahukan" in standard
    assert "memberitahukan" not in indonesian  # affixes stripped by the Indonesian stemmer
