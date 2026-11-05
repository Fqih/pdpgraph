# SPDX-License-Identifier: Apache-2.0
"""Reference resolution on the real UU 27/2022 text (M1.3, FR-PDP-03).

Needs the verified raw files: `make ingest SOURCE=uu27-2022`, then `make test-snapshot`. The
expected targets below were checked by hand against the unit text; resolver accuracy overall is
measured on the owner-labeled sample (06 §2.9).
"""

from collections import Counter
from pathlib import Path

import pytest

from pdp_ingest.pipeline import segment_source
from pdp_ingest.refs import Mention, extract_refs
from pdp_ingest.refs_review import refs_markdown
from pdp_ingest.registry import load_source
from pdp_ingest.segment import Unit

pytestmark = [pytest.mark.snapshot, pytest.mark.usefixtures("no_network")]

REPO = Path(__file__).resolve().parents[3]
S = "uu27-2022"


@pytest.fixture(scope="module")
def units() -> list[Unit]:
    entry = load_source(S, REPO / "configs" / "sources")
    *_, units = segment_source(
        entry, raw_dir=REPO / "data" / "raw", overrides_dir=REPO / "data" / "overrides"
    )
    return units


@pytest.fixture(scope="module")
def mentions(units: list[Unit]) -> list[Mention]:
    return extract_refs(units)


def _one(mentions: list[Mention], unit: str, contains: str) -> Mention:
    (m,) = [m for m in mentions if m.unit_id == f"{S}/{unit}" and contains in m.text]
    return m


def _t(*suffixes: str) -> tuple[str, ...]:
    return tuple(f"{S}/{s}" for s in suffixes)


def test_counts(mentions: list[Mention]) -> None:
    assert Counter(m.kind for m in mentions) == {"REFERENCE": 103, "DELEGATION": 11}
    assert Counter(m.resolution for m in mentions) == {
        "EXACT": 75,
        "SELF": 26,
        "EXTERNAL_UNRESOLVED": 13,
    }
    assert sum(len(m.targets) for m in mentions) == 146


def test_pasal_range(mentions: list[Mention]) -> None:
    m = _one(mentions, "p14", "sampai dengan")
    assert m.targets == _t("p6", "p7", "p8", "p9", "p10", "p11")


def test_sanction_list_with_inherited_ayat_and_ayat_range(mentions: list[Mention]) -> None:
    m = _one(mentions, "p57/a1", "Pasal 20 ayat (1)")
    assert len(m.targets) == 38
    assert m.targets[:5] == _t("p20/a1", "p21", "p24", "p25/a2", "p26/a3")
    assert m.targets[19:21] == _t("p41/a1", "p41/a3")
    assert m.targets[-3:] == _t("p56/a2", "p56/a3", "p56/a4")


def test_huruf_range_inside_list(mentions: list[Mention]) -> None:
    m = _one(mentions, "p50/a1", "Pasal 30")
    assert m.targets == _t(
        "p30",
        "p32",
        "p36",
        "p42",
        "p43/a1/ha",
        "p43/a1/hb",
        "p43/a1/hc",
        "p44/a1/hb",
        "p45",
        "p46/a1/ha",
    )


def test_relative_refs(mentions: list[Mention]) -> None:
    assert _one(mentions, "p17/a2", "huruf b").targets == _t("p17/a1/hb", "p17/a1/hc")
    assert _one(mentions, "p57/a3", "ayat (2)").targets == _t("p57/a2/hd")
    assert _one(mentions, "p48/a5", "ayat (4)").targets == _t("p48/a1", "p48/a2", "p48/a4")


def test_delegations_and_external(mentions: list[Mention]) -> None:
    delegated = Counter(m.instrument for m in mentions if m.kind == "DELEGATION")
    assert delegated == {"Peraturan Pemerintah": 10, "Peraturan Presiden": 1}
    ext = _one(mentions, "pj-umum", "Pasal 28G")
    assert ext.instrument == "Undang-Undang Dasar Negara Republik Indonesia Tahun 1945"
    assert not ext.targets


def test_committed_refs_list_is_current(mentions: list[Mention], units: list[Unit]) -> None:
    committed = REPO / "data" / "review" / S / "refs.md"
    assert committed.read_text(encoding="utf-8") == refs_markdown(S, mentions, units)
