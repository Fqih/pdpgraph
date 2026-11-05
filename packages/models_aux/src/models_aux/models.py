# SPDX-License-Identifier: Apache-2.0
"""fp32 CPU model wrappers (M0.4; 03 §4 embeddings/reranker/NLI).

Loading uses `local_files_only=True` at the pinned revision, so a missing model is an error,
never a download. Each wrapper takes a whole batch and returns one output per input.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog
import torch
from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer

from models_aux.settings import ModelsAuxSettings, ModelSpec, Task

NLI_LABELS = ("entailment", "neutral", "contradiction")

log = structlog.get_logger()


@dataclass(frozen=True)
class Models:
    embed: Callable[[list[str]], list[list[float]]]
    rerank: Callable[[list[tuple[str, str]]], list[float]]
    nli: Callable[[list[tuple[str, str]]], list[dict[str, float]]]
    dim: int
    names: dict[str, str]


def _load(model_cls: Any, spec: ModelSpec, settings: ModelsAuxSettings) -> tuple[Any, Any]:
    kw = {"revision": spec.revision, "cache_dir": settings.cache_dir, "local_files_only": True}
    try:
        tokenizer = AutoTokenizer.from_pretrained(spec.repo, **kw)
        model = model_cls.from_pretrained(spec.repo, dtype=torch.float32, **kw).eval()
    except OSError:
        raise SystemExit(
            f"{spec.repo}@{spec.revision[:12]} is not in the model cache; "
            "run `make models-download`"
        ) from None
    return tokenizer, model


def _embedder(spec: ModelSpec, settings: ModelsAuxSettings) -> tuple[Callable[..., Any], int]:
    tokenizer, model = _load(AutoModel, spec, settings)

    def embed(texts: list[str]) -> list[list[float]]:
        enc = tokenizer(
            texts, padding=True, truncation=True, max_length=spec.max_length, return_tensors="pt"
        )
        with torch.inference_mode():
            cls = model(**enc).last_hidden_state[:, 0]  # bge-m3 dense = CLS pooling
        return torch.nn.functional.normalize(cls, dim=-1).tolist()

    return embed, int(model.config.hidden_size)


def _pair_classifier(spec: ModelSpec, settings: ModelsAuxSettings) -> tuple[Any, Any]:
    tokenizer, model = _load(AutoModelForSequenceClassification, spec, settings)

    def logits(pairs: list[tuple[str, str]]) -> torch.Tensor:
        enc = tokenizer(
            [a for a, _ in pairs],
            [b for _, b in pairs],
            padding=True,
            truncation=True,
            max_length=spec.max_length,
            return_tensors="pt",
        )
        with torch.inference_mode():
            return model(**enc).logits.float()

    return logits, model.config


def _reranker(spec: ModelSpec, settings: ModelsAuxSettings) -> Callable[..., Any]:
    logits, _ = _pair_classifier(spec, settings)

    def rerank(pairs: list[tuple[str, str]]) -> list[float]:
        return torch.sigmoid(logits(pairs).view(-1)).tolist()

    return rerank


def _nli(spec: ModelSpec, settings: ModelsAuxSettings) -> Callable[..., Any]:
    logits, config = _pair_classifier(spec, settings)
    labels = [config.id2label[i].lower() for i in range(config.num_labels)]
    if sorted(labels) != sorted(NLI_LABELS):
        raise SystemExit(f"{spec.repo}: unexpected NLI labels {labels}")

    def nli(pairs: list[tuple[str, str]]) -> list[dict[str, float]]:
        probs = torch.softmax(logits(pairs), dim=-1).tolist()
        return [dict(zip(labels, row, strict=True)) for row in probs]

    return nli


def load_models(settings: ModelsAuxSettings) -> Models:
    torch.set_num_threads(settings.torch_threads)
    specs = settings.models
    seconds: dict[Task, float] = {}

    start = time.perf_counter()
    embed, dim = _embedder(specs["embed"], settings)
    seconds["embed"] = time.perf_counter() - start
    start = time.perf_counter()
    rerank = _reranker(specs["rerank"], settings)
    seconds["rerank"] = time.perf_counter() - start
    start = time.perf_counter()
    nli = _nli(specs["nli"], settings)
    seconds["nli"] = time.perf_counter() - start

    for task, s in seconds.items():
        log.info("model_loaded", task=task, repo=specs[task].repo, load_s=round(s, 2))
    return Models(
        embed=embed,
        rerank=rerank,
        nli=nli,
        dim=dim,
        names={task: spec.repo for task, spec in specs.items()},
    )
