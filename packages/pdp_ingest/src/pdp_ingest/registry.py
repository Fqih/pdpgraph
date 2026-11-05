# SPDX-License-Identifier: Apache-2.0
"""Source registry entries: `configs/sources/<source_id>.yaml` (04 §1, SEC-14)."""

from datetime import date
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, field_validator

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
InstrumentType = Literal["UU", "PP", "PERPRES", "PERMEN", "PERBAN", "PUTUSAN_MK", "OTHER"]


def _https(url: HttpUrl) -> HttpUrl:
    if url.scheme != "https":
        raise ValueError("source URLs must use https")
    return url


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PrimarySource(_Strict):
    """Text source. The registry verifies the law body: the inner HTML of `body_element_id`.
    `snapshot_sha256` identifies the archived raw page (raw bytes vary per fetch)."""

    url: HttpUrl
    format: Literal["html"]
    body_element_id: str = Field(min_length=1)
    body_sha256: Sha256
    snapshot_sha256: Sha256

    _https = field_validator("url")(_https)


class ReferenceSource(_Strict):
    """Authoritative document used to cross-check the primary text (M1.2)."""

    format: Literal["pdf"]
    sha256: Sha256
    urls: list[HttpUrl] = Field(min_length=1)  # official mirrors, tried in order

    @field_validator("urls")
    @classmethod
    def _all_https(cls, urls: list[HttpUrl]) -> list[HttpUrl]:
        return [_https(u) for u in urls]


class SourceEntry(_Strict):
    source_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
    title: str = Field(min_length=1)
    instrument_type: InstrumentType
    number: int
    year: int
    enacted_on: date
    promulgated_on: date
    effective_from: date
    primary: PrimarySource
    reference: ReferenceSource


def load_source(source_id: str, registry_dir: Path) -> SourceEntry:
    path = registry_dir / f"{source_id}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"no registry entry for {source_id!r} in {registry_dir}")
    entry = SourceEntry.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if entry.source_id != source_id:
        raise ValueError(f"{path.name} declares source_id {entry.source_id!r}")
    return entry
