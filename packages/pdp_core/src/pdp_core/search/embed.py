# SPDX-License-Identifier: Apache-2.0
"""models-aux `/embed` client (05 §4, M1.6)."""

from dataclasses import dataclass
from typing import Literal

import httpx


@dataclass(frozen=True)
class Embedded:
    model: str
    revision: str
    dim: int
    vectors: list[list[float]]
    multi_vectors: list[list[list[float]]] | None


def embed(
    http: httpx.Client,
    texts: list[str],
    kind: Literal["query", "passage"],
    *,
    multi_vector: bool = False,
) -> Embedded:
    body = {"inputs": texts, "kind": kind, "multi_vector": multi_vector}
    r = http.post("/embed", json=body)
    r.raise_for_status()
    out = r.json()
    return Embedded(
        out["model"], out["revision"], out["dim"], out["vectors"], out.get("multi_vectors")
    )
