# SPDX-License-Identifier: Apache-2.0
"""Content invariants and canonical hash on the real UU 27/2022 snapshot (M1.1, EV-03).

Needs the verified raw files: `make ingest SOURCE=uu27-2022`, then `make test-snapshot`.
"""

from pathlib import Path

import pytest

from pdp_ingest.canonical import blocks, canonical_sha256, check_invariants
from pdp_ingest.fetch import element_inner_html, load_verified
from pdp_ingest.registry import load_source

pytestmark = [pytest.mark.snapshot, pytest.mark.usefixtures("no_network")]

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def body() -> str:
    entry = load_source("uu27-2022", REPO / "configs" / "sources")
    html_path, _ = load_verified(entry, REPO / "data" / "raw")
    return element_inner_html(html_path.read_text(encoding="utf-8"), entry.primary.body_element_id)


def test_invariants_hold(body: str) -> None:
    entry = load_source("uu27-2022", REPO / "configs" / "sources")
    report = check_invariants(blocks(body), entry.primary.invariants)
    print(report)
    assert report["bab_headings"] == 16
    assert report["pasal_headings_body"] == report["pasal_headings_explanation"] == 76
    assert report["cukup_jelas"] == 126
    assert report["items"] == ["Pasal 4 path [3, 3] = 'kewarganegaraan;'"]


def test_canonical_hash_matches_registry(body: str) -> None:
    entry = load_source("uu27-2022", REPO / "configs" / "sources")
    assert canonical_sha256(body) == entry.primary.body_sha256
