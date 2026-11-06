# SPDX-License-Identifier: Apache-2.0
"""configs/models_aux.yaml: pinned revisions and licences (M0.4)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from models_aux.settings import ModelsAuxSettings, ModelSpec


def test_config_pins_three_models_by_commit_hash() -> None:
    models = ModelsAuxSettings().models
    assert set(models) == {"embed", "rerank", "nli"}
    assert models["embed"].repo == "BAAI/bge-m3"
    assert models["rerank"].repo == "BAAI/bge-reranker-v2-m3"
    assert models["nli"].repo == "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
    for spec in models.values():
        assert len(spec.revision) == 40
        assert spec.license
        assert spec.allow_patterns


def test_only_safetensors_weights_or_pinned_heads_are_fetched() -> None:
    for spec in ModelsAuxSettings().models.values():
        assert "model.safetensors" in spec.allow_patterns
        pickled = [p for p in spec.allow_patterns if p.endswith((".bin", ".pt", ".pth", ".pkl"))]
        # a pickled file is fetched only when pinned by sha256 and read without unpickling
        assert set(pickled) <= set(spec.pinned_sha256), pickled


def test_bge_m3_colbert_head_is_pinned() -> None:
    embed = ModelsAuxSettings().models["embed"]
    assert embed.pinned_sha256 == {
        "colbert_linear.pt": "19bfbae397c2b7524158c919d0e9b19393c5639d098f0a66932c91ed8f5f9abb"
    }


def test_pinned_file_must_be_fetched() -> None:
    with pytest.raises(ValidationError, match="not in allow_patterns"):
        ModelSpec(
            repo="x/y",
            revision="a" * 40,
            license="MIT",
            max_length=512,
            allow_patterns=["model.safetensors"],
            pinned_sha256={"head.pt": "b" * 64},
        )


@pytest.mark.parametrize("revision", ["main", "v1.0", "5617a9f", "Z" * 40])
def test_revision_must_be_a_commit_hash(revision: str) -> None:
    with pytest.raises(ValidationError, match="revision"):
        ModelSpec(
            repo="x/y", revision=revision, license="MIT", max_length=512, allow_patterns=["*"]
        )


def test_cache_dir_is_outside_the_repo() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    assert not ModelsAuxSettings().cache_dir.resolve().is_relative_to(repo_root)
