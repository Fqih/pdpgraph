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


@pytest.mark.parametrize("revision", ["main", "v1.0", "5617a9f", "Z" * 40])
def test_revision_must_be_a_commit_hash(revision: str) -> None:
    with pytest.raises(ValidationError, match="revision"):
        ModelSpec(
            repo="x/y", revision=revision, license="MIT", max_length=512, allow_patterns=["*"]
        )


def test_cache_dir_is_outside_the_repo() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    assert not ModelsAuxSettings().cache_dir.resolve().is_relative_to(repo_root)
