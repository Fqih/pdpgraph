# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for common/ tests."""

import socket

import pytest


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if anything tries to open a network connection."""

    def _blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access attempted in a test")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
