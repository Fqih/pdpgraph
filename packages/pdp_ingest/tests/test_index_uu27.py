# SPDX-License-Identifier: Apache-2.0
"""UU 27/2022 index documents and the committed index body (M1.6, FR-PDP-07).

Needs the verified raw files: `make ingest SOURCE=uu27-2022`, then `make test-snapshot`.
"""

import json
from pathlib import Path

import pytest
import yaml

from pdp_core.search import protected_keywords
from pdp_ingest.index import build_documents
from pdp_ingest.pipeline import run_text_stages
from pdp_ingest.registry import load_source

pytestmark = [pytest.mark.snapshot, pytest.mark.usefixtures("no_network")]

REPO = Path(__file__).resolve().parents[3]
S = "uu27-2022"
BODY = REPO / "tests" / "fixtures" / S / "legal_units.index.json"


@pytest.fixture(scope="module")
def processed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("processed")
    entry = load_source(S, REPO / "configs" / "sources")
    run_text_stages(
        entry,
        raw_dir=REPO / "data" / "raw",
        overrides_dir=REPO / "data" / "overrides",
        processed_dir=out,
    )
    return out / S


def test_committed_body_keywords_match_fresh_terms(processed: Path) -> None:
    body = json.loads(BODY.read_text(encoding="utf-8"))
    terms = json.loads((processed / "terms.json").read_text(encoding="utf-8"))
    keywords = body["settings"]["analysis"]["filter"]["protected_terms"]["keywords"]
    assert keywords == protected_keywords(terms)
    assert {"pengendali", "pribadi", "prosesor"} <= set(keywords)


def test_committed_body_pins_the_configured_embedding_model() -> None:
    meta = json.loads(BODY.read_text(encoding="utf-8"))["mappings"]["_meta"]
    embed = yaml.safe_load((REPO / "configs" / "models_aux.yaml").read_text())["models"]["embed"]
    assert (meta["embedding_model"], meta["embedding_revision"]) == (
        embed["repo"],
        embed["revision"],
    )
    assert meta["embedding_dim"] == 1024


def test_documents(processed: Path) -> None:
    docs = {d["unit_id"]: d for d in build_documents(processed)}
    kinds: dict[str, int] = {}
    for d in docs.values():
        kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
    # 04 §4: Pasal only without ayat (42 with ayat skipped); Penjelasan only when substantive
    # (126 "Cukup jelas" skipped)
    assert kinds == {"PASAL": 34, "AYAT": 122, "HURUF": 144, "ANGKA": 13, "PENJELASAN": 38}
    pj = docs[f"{S}/p4/a2/ha#pj"]
    assert pj["explains"] == f"{S}/p4/a2/ha"
    assert "explains" not in docs[f"{S}/pj-umum"]
    p46 = docs[f"{S}/p46/a1"]
    assert p46["context_text"].endswith(" / Pasal 46 ayat (1)")
    assert "pengendali data pribadi" in p46["terms"]
    assert f"{S}/p46" not in docs  # has ayat
    assert not any(d["text"].startswith("Cukup jelas") for d in docs.values())
    huruf = docs[f"{S}/p4/a2/ha"]
    assert huruf["embedding_input"].startswith("Data Pribadi yang bersifat spesifik")
