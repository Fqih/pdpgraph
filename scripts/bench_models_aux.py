# SPDX-License-Identifier: Apache-2.0
"""Latency benchmark for a running models-aux service (M0.4).

Usage: uv run --frozen python scripts/bench_models_aux.py [--url URL] [--runs N]
Sequential requests after a warm-up; prints p50/p95 per scenario in milliseconds as JSON.
Texts are synthetic.
"""

import argparse
import json
import statistics
import time
from typing import Any

import httpx

SENTENCE = (
    "Pengendali Data Pribadi wajib memastikan pemrosesan data pribadi dilakukan secara terbatas, "
    "spesifik, sah, dan transparan sesuai dengan tujuan yang telah disetujui, termasuk ketentuan "
    "nomor {i} tentang penyimpanan, akurasi, dan pemusnahan data."
)
QUERY = "Apa kewajiban pengendali data pribadi saat memproses data?"


def _passages(n: int) -> list[str]:
    return [SENTENCE.format(i=i) for i in range(n)]


SCENARIOS: dict[str, tuple[str, dict[str, Any]]] = {
    "embed_1_query": ("/embed", {"inputs": [QUERY], "kind": "query"}),
    "embed_32_passages": ("/embed", {"inputs": _passages(32), "kind": "passage"}),
    "rerank_1x30": ("/rerank", {"query": QUERY, "passages": _passages(30)}),
    "nli_8_pairs": (
        "/nli",
        {"pairs": [{"premise": p, "hypothesis": QUERY} for p in _passages(8)]},
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8070")
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=3)
    args = parser.parse_args()
    results: dict[str, dict[str, float]] = {}
    with httpx.Client(base_url=args.url, timeout=300) as client:
        for name, (path, body) in SCENARIOS.items():
            for _ in range(args.warmup):
                client.post(path, json=body).raise_for_status()
            samples = []
            for _ in range(args.runs):
                start = time.perf_counter()
                client.post(path, json=body).raise_for_status()
                samples.append((time.perf_counter() - start) * 1000)
            cuts = statistics.quantiles(samples, n=100, method="inclusive")
            results[name] = {"p50_ms": round(cuts[49], 1), "p95_ms": round(cuts[94], 1)}
    print(json.dumps({"runs": args.runs, "warmup": args.warmup, "results": results}, indent=2))


if __name__ == "__main__":
    main()
