# SPDX-License-Identifier: Apache-2.0
"""The committed text-free structure of UU 27/2022 equals a fresh ingest (M1.5).

`tests/fixtures/uu27-2022/structure.json` feeds the real-graph tests in CI; this keeps it from
drifting. Needs the verified raw files (`make ingest SOURCE=uu27-2022`, then
`make test-snapshot`). Regenerate after an intended change with
`uv run python -m pdp_ingest.graph_load --source uu27-2022 --export-structure <path>`.
"""

import json
from pathlib import Path

import pytest

from pdp_ingest.graph_load import read_graph
from pdp_ingest.graph_structure import write_structure
from pdp_ingest.pipeline import run_text_stages
from pdp_ingest.registry import load_source

pytestmark = [pytest.mark.snapshot, pytest.mark.usefixtures("no_network")]

REPO = Path(__file__).resolve().parents[3]
S = "uu27-2022"
COMMITTED = REPO / "tests" / "fixtures" / S / "structure.json"


def test_committed_structure_matches_fresh_ingest(tmp_path: Path) -> None:
    entry = load_source(S, REPO / "configs" / "sources")
    run_text_stages(
        entry,
        raw_dir=REPO / "data" / "raw",
        overrides_dir=REPO / "data" / "overrides",
        processed_dir=tmp_path,
    )
    fresh = tmp_path / "structure.json"
    write_structure(read_graph(tmp_path / S, REPO / "data" / "review" / S), fresh)
    if fresh.read_bytes() != COMMITTED.read_bytes():
        got, want = json.loads(fresh.read_text()), json.loads(COMMITTED.read_text())
        changed = sorted(k for k in want.keys() | got.keys() if got.get(k) != want.get(k))
        pytest.fail(f"{COMMITTED.name} is stale; changed groups: {changed}. Regenerate it.")
