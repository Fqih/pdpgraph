# SPDX-License-Identifier: Apache-2.0
"""models-aux on the real pinned weights, offline (M0.4 DoD: correct dims and scores).

Run with `make test-models` after `make models-download`. Fixtures are synthetic paraphrases.
"""

import math
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from models_aux.app import create_app
from models_aux.models import load_models
from models_aux.settings import ModelsAuxSettings

pytestmark = [pytest.mark.models, pytest.mark.usefixtures("no_network")]

QUERY = "Kapan pengendali data pribadi wajib memberitahukan kegagalan pelindungan data?"
RELEVANT = (
    "Pengendali Data Pribadi wajib menyampaikan pemberitahuan tertulis paling lambat 3 x 24 jam "
    "kepada Subjek Data Pribadi dan lembaga dalam hal terjadi kegagalan Pelindungan Data Pribadi."
)
IRRELEVANT = "Pajak kendaraan bermotor dibayar setiap tahun di kantor Samsat terdekat."


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    settings = ModelsAuxSettings()
    with TestClient(create_app(load_models(settings), settings)) as c:
        yield c


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_embed_dims_norm_and_ranking(client: TestClient) -> None:
    q = client.post("/embed", json={"inputs": [QUERY], "kind": "query"}).json()
    p = client.post("/embed", json={"inputs": [RELEVANT, IRRELEVANT], "kind": "passage"}).json()
    assert q["model"] == "BAAI/bge-m3"
    assert q["dim"] == p["dim"] == 1024
    assert all(len(v) == 1024 for v in q["vectors"] + p["vectors"])
    assert all(math.isclose(_cos(v, v), 1.0, rel_tol=1e-4) for v in p["vectors"])
    (qv,) = q["vectors"]
    assert _cos(qv, p["vectors"][0]) > _cos(qv, p["vectors"][1]) + 0.1


def test_rerank_scores_relevant_first(client: TestClient) -> None:
    r = client.post("/rerank", json={"query": QUERY, "passages": [IRRELEVANT, RELEVANT]}).json()
    assert r["model"] == "BAAI/bge-reranker-v2-m3"
    irrelevant, relevant = r["scores"]
    assert all(0.0 <= s <= 1.0 for s in r["scores"])
    assert relevant > 0.5 > irrelevant


@pytest.mark.parametrize(
    ("hypothesis", "expected"),
    [
        (
            "Pemberitahuan kegagalan pelindungan data disampaikan paling lambat 3 x 24 jam.",
            "entailment",
        ),
        (
            "Pengendali tidak perlu memberi tahu siapa pun saat terjadi kegagalan "
            "pelindungan data.",
            "contradiction",
        ),
    ],
)
def test_nli_labels(client: TestClient, hypothesis: str, expected: str) -> None:
    r = client.post(
        "/nli", json={"pairs": [{"premise": RELEVANT, "hypothesis": hypothesis}]}
    ).json()
    (probs,) = r["results"]
    assert set(probs) == {"entailment", "neutral", "contradiction"}
    assert math.isclose(sum(probs.values()), 1.0, rel_tol=1e-4)
    assert max(probs, key=probs.__getitem__) == expected
