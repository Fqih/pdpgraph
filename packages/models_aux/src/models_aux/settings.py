# SPDX-License-Identifier: Apache-2.0
"""models-aux settings: `configs/models_aux.yaml`, overridable by `MODELS_AUX_*` env vars."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic_settings import SettingsConfigDict

from common.config import YamlSettings

Task = Literal["embed", "rerank", "nli"]


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repo: str
    revision: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]  # commit hash only
    license: str = Field(min_length=1)
    max_length: int = Field(gt=0)
    allow_patterns: list[str] = Field(min_length=1)
    # file -> SHA-256 of files that are not safetensors; read without unpickling (ADR-020)
    pinned_sha256: dict[str, Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]] = {}

    @model_validator(mode="after")
    def _pinned_are_fetched(self) -> "ModelSpec":
        if missing := sorted(set(self.pinned_sha256) - set(self.allow_patterns)):
            raise ValueError(f"pinned files not in allow_patterns: {missing}")
        return self


class ModelsAuxSettings(YamlSettings):
    model_config = SettingsConfigDict(env_prefix="MODELS_AUX_", yaml_file="configs/models_aux.yaml")

    # Outside the repo; mounted read-only into the container.
    cache_dir: Path = Path.home() / ".cache" / "pdpgraph" / "models"
    host: str = "127.0.0.1"
    port: int = 8070
    torch_threads: int = Field(gt=0)
    max_batch: int = Field(gt=0)
    max_wait_ms: float = Field(ge=0)
    max_inputs: int = Field(gt=0)
    max_chars: int = Field(gt=0)
    models: dict[Task, ModelSpec]
