# SPDX-License-Identifier: Apache-2.0
"""models-aux HTTP contract (05 §4) against fake models."""

import uuid

import pytest
from fastapi.testclient import TestClient


def test_embed_shape(client: TestClient) -> None:
    r = client.post("/embed", json={"inputs": ["a", "bcd"], "kind": "passage"})
    assert r.status_code == 200
    assert r.json() == {
        "model": "fake/embed",
        "revision": "f" * 40,
        "dim": 2,
        "vectors": [[1.0, 1.0], [3.0, 1.0]],
    }


def test_embed_multi_vector(client: TestClient, calls: dict[str, list[int]]) -> None:
    r = client.post(
        "/embed", json={"inputs": ["a", "bcd"], "kind": "passage", "multi_vector": True}
    )
    body = r.json()
    assert body["vectors"] == [[1.0, 1.0], [3.0, 1.0]]
    # one vector per token: the fake has one token per character
    assert body["multi_vectors"] == [[[1.0, 0.0]], [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]]
    assert calls["embed_multi"] == [2]
    assert "embed" not in calls


def test_embed_without_multi_vector_has_no_multi_vectors(client: TestClient) -> None:
    body = client.post("/embed", json={"inputs": ["a"], "kind": "query"}).json()
    assert "multi_vectors" not in body


def test_rerank_scores_follow_passage_order(client: TestClient) -> None:
    body = {"query": "pengendali data", "passages": ["lain", "pengendali wajib", "x"]}
    r = client.post("/rerank", json=body)
    assert r.json() == {"model": "fake/rerank", "scores": [0.0, 1.0, 0.0]}


def test_nli_results(client: TestClient) -> None:
    pairs = [{"premise": "A dan B", "hypothesis": "A"}, {"premise": "A", "hypothesis": "C"}]
    r = client.post("/nli", json={"pairs": pairs})
    results = r.json()["results"]
    assert r.json()["model"] == "fake/nli"
    assert results[0]["entailment"] > results[0]["contradiction"]
    assert results[1]["contradiction"] > results[1]["entailment"]
    assert set(results[0]) == {"entailment", "neutral", "contradiction"}


def test_request_items_run_as_one_batch(client: TestClient, calls: dict[str, list[int]]) -> None:
    r = client.post("/embed", json={"inputs": ["x"] * 5, "kind": "query"})
    assert r.status_code == 200
    assert calls["embed"] == [5]


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/embed", {"inputs": [], "kind": "query"}),
        ("/embed", {"inputs": ["a"], "kind": "document"}),
        ("/embed", {"inputs": [""], "kind": "query"}),
        ("/embed", {"inputs": ["a"] * 65, "kind": "query"}),
        ("/embed", {"inputs": ["a" * 8001], "kind": "query"}),
        ("/rerank", {"query": "q", "passages": []}),
        ("/nli", {"pairs": [{"premise": "p"}]}),
        ("/embed", {"inputs": ["a"], "kind": "query", "extra": 1}),
    ],
)
def test_invalid_requests_use_error_envelope(client: TestClient, path: str, body: object) -> None:
    r = client.post(path, json=body)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "invalid_request"
    assert err["request_id"] == r.headers["x-request-id"]
    assert "a" * 100 not in r.text  # offending input is never echoed


def test_request_id_is_echoed_or_generated(client: TestClient) -> None:
    rid = str(uuid.uuid4())
    r = client.post(
        "/embed", json={"inputs": ["a"], "kind": "query"}, headers={"x-request-id": rid}
    )
    assert r.headers["x-request-id"] == rid
    generated = client.get("/healthz").headers["x-request-id"]
    assert uuid.UUID(generated)
    bogus = client.get("/healthz", headers={"x-request-id": "not-a-uuid"}).headers["x-request-id"]
    assert bogus != "not-a-uuid"


def test_unknown_path_uses_error_envelope(client: TestClient) -> None:
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_model_failure_is_a_500_without_details(client: TestClient) -> None:
    r = client.post("/nli", json={"pairs": [{"premise": "p", "hypothesis": "BOOM"}]})
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "secret-path" not in r.text
    ok = client.post("/nli", json={"pairs": [{"premise": "p", "hypothesis": "p"}]})
    assert ok.status_code == 200


def test_healthz(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
