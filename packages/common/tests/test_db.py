# SPDX-License-Identifier: Apache-2.0
"""Postgres settings: same POSTGRES_* variables as compose, password never printed (SEC-11)."""

import pytest

from common.db import PostgresSettings


def test_url_from_env_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw-local-1")
    monkeypatch.setenv("POSTGRES_PORT", "6543")
    s = PostgresSettings(_env_file=None)
    url = s.url()
    assert url.drivername == "postgresql+psycopg"
    assert (url.host, url.port, url.username, url.database) == (
        "127.0.0.1",
        6543,
        "pdpgraph",
        "pdpgraph",
    )
    assert url.password == "pw-local-1"  # noqa: S105 - synthetic test value


def test_password_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="password"):
        PostgresSettings(_env_file=None)


def test_password_never_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw-local-1")
    s = PostgresSettings(_env_file=None)
    assert "pw-local-1" not in repr(s)
    assert "pw-local-1" not in str(s.url())
