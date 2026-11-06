# SPDX-License-Identifier: Apache-2.0
"""04-data-model §3.3/§3.4 and `pdp_core/graph` must not drift apart (M1.5). No database needed."""

import re
from pathlib import Path

from pdp_core.graph import CONSTRAINTS, QUERIES

ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / ".context" / "04-data-model.md").read_text(encoding="utf-8")


def _section(heading: str) -> str:
    return SPEC.split(heading, 1)[1].split("\n### ", 1)[0]


def test_constraints_equal_spec_block() -> None:
    (block,) = re.findall(r"```cypher\n(.*?)```", _section("### 3.3 Constraints"), re.DOTALL)
    spec = [s.strip() for s in block.split(";") if s.strip()]
    assert spec == list(CONSTRAINTS)


def test_every_canonical_query_is_implemented() -> None:
    names = re.findall(r"^- `(\w+)\(", _section("### 3.4 Canonical queries"), re.MULTILINE)
    assert names
    assert set(names) <= set(QUERIES)
