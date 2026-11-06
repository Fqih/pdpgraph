# SPDX-License-Identifier: Apache-2.0
"""fp32 CPU model wrappers (M0.4; 03 §4 embeddings/reranker/NLI).

Loading uses `local_files_only=True` at the pinned revision, so a missing model is an error,
never a download. Each wrapper takes a whole batch and returns one output per input.
"""

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
import torch
from safetensors.torch import load_file
from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer

from models_aux.convert import converted_dir
from models_aux.settings import ModelsAuxSettings, ModelSpec, Task

NLI_LABELS = ("entailment", "neutral", "contradiction")
COLBERT_FILE = "colbert_linear.pt"  # converted to safetensors by make models-download
PICKLED = (".pt", ".pth", ".bin", ".pkl")
Multi = tuple[list[float], list[list[float]]]  # dense vector, one vector per token

log = structlog.get_logger()


@dataclass(frozen=True)
class Models:
    embed: Callable[[list[str]], list[list[float]]]
    embed_multi: Callable[[list[str]], list[Multi]]
    rerank: Callable[[list[tuple[str, str]]], list[float]]
    nli: Callable[[list[tuple[str, str]]], list[dict[str, float]]]
    dim: int
    names: dict[str, str]
    revisions: dict[str, str]


def _load(model_cls: Any, spec: ModelSpec, settings: ModelsAuxSettings) -> tuple[Any, Any]:
    kw = {"revision": spec.revision, "cache_dir": settings.cache_dir, "local_files_only": True}
    try:
        tokenizer = AutoTokenizer.from_pretrained(spec.repo, **kw)
        model = model_cls.from_pretrained(
            spec.repo, dtype=torch.float32, use_safetensors=True, **kw
        ).eval()  # never unpickle weights (SEC-13)
    except OSError:
        raise SystemExit(
            f"{spec.repo}@{spec.revision[:12]} is not in the model cache; "
            "run `make models-download`"
        ) from None
    return tokenizer, model


def load_safetensors(path: Path, sha256: str) -> dict[str, torch.Tensor]:
    """The only runtime loader for converted files: safetensors at the pinned hash, never a
    pickle (ADR-020, SEC-13)."""
    if path.suffix != ".safetensors" or path.suffix in PICKLED:
        raise ValueError(f"{path.name}: refusing a pickle-format file at runtime")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != sha256:
        raise ValueError(f"{path.name}: sha256 {actual} is not the pinned {sha256}")
    return load_file(path)


def _colbert_head(spec: ModelSpec, settings: ModelsAuxSettings, dim: int) -> torch.nn.Linear:
    conv = spec.convert[COLBERT_FILE]
    path = converted_dir(settings.cache_dir, spec.repo, spec.revision) / conv.output
    if not path.is_file():
        raise SystemExit(f"{path} is missing; run `make models-download`")
    state = load_safetensors(path, conv.output_sha256)
    head = torch.nn.Linear(dim, dim)
    with torch.no_grad():
        head.weight.copy_(state["weight"].float())
        head.bias.copy_(state["bias"].float())
    return head.eval()


def _embedder(
    spec: ModelSpec, settings: ModelsAuxSettings
) -> tuple[Callable[..., Any], Callable[..., Any], int]:
    tokenizer, model = _load(AutoModel, spec, settings)
    dim = int(model.config.hidden_size)
    head = _colbert_head(spec, settings, dim)
    normalize = torch.nn.functional.normalize

    def hidden(texts: list[str]) -> tuple[torch.Tensor, torch.Tensor]:
        enc = tokenizer(
            texts, padding=True, truncation=True, max_length=spec.max_length, return_tensors="pt"
        )
        return model(**enc).last_hidden_state, enc["attention_mask"]

    def embed(texts: list[str]) -> list[list[float]]:
        with torch.inference_mode():
            h, _ = hidden(texts)
        return normalize(h[:, 0], dim=-1).tolist()  # bge-m3 dense = CLS pooling

    def embed_multi(texts: list[str]) -> list[Multi]:
        # bge-m3 ColBERT: head over every token after CLS, L2-normalized, padding dropped
        with torch.inference_mode():
            h, mask = hidden(texts)
            dense = normalize(h[:, 0], dim=-1)
            tokens = normalize(head(h[:, 1:]), dim=-1)
        lengths = (mask.sum(dim=1) - 1).tolist()
        return [(dense[i].tolist(), tokens[i, :n].tolist()) for i, n in enumerate(lengths)]

    return embed, embed_multi, dim


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
    embed, embed_multi, dim = _embedder(specs["embed"], settings)
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
        embed_multi=embed_multi,
        rerank=rerank,
        nli=nli,
        dim=dim,
        names={task: spec.repo for task, spec in specs.items()},
        revisions={task: spec.revision for task, spec in specs.items()},
    )
