# SPDX-License-Identifier: Apache-2.0
"""Source registry entries (04 §1, SEC-14)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from pdp_ingest.registry import SourceEntry, load_source

REPO = Path(__file__).resolve().parents[3]


def test_uu27_entry_pins_body_snapshot_and_reference() -> None:
    entry = load_source("uu27-2022", REPO / "configs" / "sources")
    assert entry.instrument_type == "UU"
    assert (entry.number, entry.year) == (27, 2022)
    assert str(entry.promulgated_on) == "2022-10-17"
    assert entry.primary.format == "html"
    assert entry.primary.body_element_id == "produk-content"
    assert entry.primary.body_sha256.startswith("36f26c29")
    assert entry.reference.sha256.startswith("ed952dea")
    assert len(entry.reference.urls) >= 2


def test_unknown_source_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no registry entry for 'nope'"):
        load_source("nope", tmp_path)


def _entry(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "source_id": "uu27-2022",
        "title": "t",
        "instrument_type": "UU",
        "number": 27,
        "year": 2022,
        "enacted_on": "2022-10-17",
        "promulgated_on": "2022-10-17",
        "effective_from": "2022-10-17",
        "primary": {
            "url": "https://example.go.id/x",
            "format": "html",
            "body_element_id": "c",
            "body_sha256": "a" * 64,
            "snapshot_sha256": "b" * 64,
        },
        "reference": {"format": "pdf", "sha256": "c" * 64, "urls": ["https://example.go.id/r.pdf"]},
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_id": "UU 27"},
        {"instrument_type": "LAW"},
        {"primary": {**_entry()["primary"], "body_sha256": "abc"}},  # type: ignore[dict-item]
        {"primary": {**_entry()["primary"], "url": "http://example.go.id/x"}},  # type: ignore[dict-item]
        {"reference": {"format": "pdf", "sha256": "c" * 64, "urls": []}},
        {"extra": 1},
    ],
)
def test_invalid_entries_rejected(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SourceEntry.model_validate(_entry(**overrides))


def test_putusan_mk_is_a_valid_instrument_type() -> None:
    assert SourceEntry.model_validate(_entry(instrument_type="PUTUSAN_MK")).instrument_type == (
        "PUTUSAN_MK"
    )
