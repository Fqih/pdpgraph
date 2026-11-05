# SPDX-License-Identifier: Apache-2.0
"""LLMClient settings (`LLM_*` env vars, 08 Phase 1 note) and the data-class enum (FR-PDP-18)."""

from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

import httpx
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import SettingsConfigDict

from common.config import YamlSettings

Mode = Literal["replay", "record", "live"]

# Set by the client itself; config may not override them.
RESERVED_HEADERS = frozenset({"authorization", "content-type", "x-data-class", "x-tierline-task"})


class DataClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    PII = "pii"


# Sent only to hosts in `local_base_urls` (ADR-013/015). Tierline policy (M2) and the 9router
# catalog (M0.7) tighten this further; never relax it.
LOCAL_ONLY = frozenset({DataClass.CONFIDENTIAL, DataClass.PII})


class LLMSettings(YamlSettings):
    """`replay` (default) never touches the network; `record` calls upstream and writes
    cassettes; `live` calls upstream and writes nothing."""

    model_config = SettingsConfigDict(env_prefix="LLM_")

    mode: Mode = "replay"
    base_url: str | None = None
    api_key: SecretStr | None = None
    model: str
    connect_timeout_s: float = 5.0  # [TUNE]
    read_timeout_s: float = 120.0  # [TUNE] CPU-bound local tiers are slow
    extra_headers: dict[str, str] = Field(default_factory=dict)
    cassette_dir: Path = Path("evals/cassettes")
    cassette_namespace: str = "default"
    # Hosts (not full URLs) treated as local; matched exactly against the base_url host.
    local_base_urls: list[str] = Field(default_factory=lambda: ["127.0.0.1", "::1", "localhost"])

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.mode != "replay" and not self.base_url:
            raise ValueError(f"base_url is required in {self.mode} mode")
        reserved = sorted(h for h in self.extra_headers if h.lower() in RESERVED_HEADERS)
        if reserved:
            raise ValueError(f"extra_headers may not set reserved headers: {reserved}")
        return self

    def is_local_endpoint(self) -> bool:
        if not self.base_url:
            return False
        host = httpx.URL(self.base_url).host.lower()
        return host in {h.lower() for h in self.local_base_urls}

    def secret_values(self) -> tuple[str, ...]:
        """Values that must never reach cassettes, traces, or logs (pass to `configure_logging`)."""
        values: set[str] = set()
        if self.base_url:
            url = httpx.URL(self.base_url)
            values |= {self.base_url, url.host, url.netloc.decode("ascii")}
        if self.api_key is not None:
            values.add(self.api_key.get_secret_value())
        return tuple(v for v in values if v)
