# SPDX-License-Identifier: Apache-2.0
"""models-aux on the real pinned weights, offline (M0.4 DoD: correct dims and scores).

Run with `make test-models` after `make models-download`. Fixtures are synthetic paraphrases.
"""

import math
from collections.abc import Iterator

import pytest
import torch
from fastapi.testclient import TestClient
from huggingface_hub import hf_hub_download

from models_aux.app import create_app
from models_aux.convert import converted_dir
from models_aux.models import COLBERT_FILE, load_models, load_safetensors
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


def test_embed_multi_vector_tokens(client: TestClient) -> None:
    plain = client.post("/embed", json={"inputs": [RELEVANT], "kind": "passage"}).json()
    body = {"inputs": [RELEVANT, IRRELEVANT], "kind": "passage", "multi_vector": True}
    r = client.post("/embed", json=body).json()
    assert r["revision"] == "7b44caba5c06fd6f1ef1d2786261e636c38e4295"
    assert math.isclose(_cos(r["vectors"][0], plain["vectors"][0]), 1.0, rel_tol=1e-5)
    long, short = r["multi_vectors"]
    assert len(long) > len(short) > 5  # one vector per token after CLS, padding dropped
    assert all(len(v) == 1024 and math.isclose(_cos(v, v), 1.0, rel_tol=1e-4) for v in long)


def test_converted_colbert_head_is_bit_identical_to_reference_load() -> None:
    """ADR-020: the safetensors head equals torch.load(weights_only=True) of the pinned .pt.
    Test-only reference load; the service never loads the pickle."""
    settings = ModelsAuxSettings()
    spec = settings.models["embed"]
    conv = spec.convert[COLBERT_FILE]
    src = hf_hub_download(
        spec.repo,
        COLBERT_FILE,
        revision=spec.revision,
        cache_dir=settings.cache_dir,
        local_files_only=True,
    )
    reference = torch.load(src, weights_only=True, map_location="cpu")
    out = converted_dir(settings.cache_dir, spec.repo, spec.revision) / conv.output
    converted = load_safetensors(out, conv.output_sha256)
    assert set(converted) == set(reference) == {"weight", "bias"}
    assert all(torch.equal(converted[k], reference[k]) for k in reference)


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
