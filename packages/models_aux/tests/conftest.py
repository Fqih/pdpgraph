# SPDX-License-Identifier: Apache-2.0
"""Fake models so API and batching tests need no weights."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from models_aux.app import create_app
from models_aux.models import Models
from models_aux.settings import ModelsAuxSettings

CALLS: dict[str, list[int]] = {}


def _embed(texts: list[str]) -> list[list[float]]:
    CALLS.setdefault("embed", []).append(len(texts))
    return [[float(len(t)), 1.0] for t in texts]


def _rerank(pairs: list[tuple[str, str]]) -> list[float]:
    CALLS.setdefault("rerank", []).append(len(pairs))
    return [1.0 if q.split()[0] in p else 0.0 for q, p in pairs]


def _nli(pairs: list[tuple[str, str]]) -> list[dict[str, float]]:
    CALLS.setdefault("nli", []).append(len(pairs))
    if any(h == "BOOM" for _, h in pairs):
        raise RuntimeError("internal detail: /models/secret-path")
    return [
        {"entailment": 0.8, "neutral": 0.15, "contradiction": 0.05}
        if h in p
        else {"entailment": 0.05, "neutral": 0.15, "contradiction": 0.8}
        for p, h in pairs
    ]


FAKE = Models(
    embed=_embed,
    rerank=_rerank,
    nli=_nli,
    dim=2,
    names={"embed": "fake/embed", "rerank": "fake/rerank", "nli": "fake/nli"},
)


@pytest.fixture
def settings() -> ModelsAuxSettings:
    return ModelsAuxSettings()


@pytest.fixture
def calls() -> dict[str, list[int]]:
    return CALLS


@pytest.fixture
def client(settings: ModelsAuxSettings) -> Iterator[TestClient]:
    CALLS.clear()
    with TestClient(create_app(FAKE, settings)) as c:
        yield c
