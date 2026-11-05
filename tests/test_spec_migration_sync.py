# SPDX-License-Identifier: Apache-2.0
"""04-data-model §6 SQL and migration 0001 must not drift apart (M0.6).

The spec block and the SQL executed by `0001_initial.py` are compared after removing comments
and normalizing whitespace. No database needed.
"""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / ".context" / "04-data-model.md"
MIGRATION = ROOT / "migrations" / "versions" / "0001_initial.py"


def _spec_sql() -> str:
    text = SPEC.read_text(encoding="utf-8")
    section = text.split("## 6. Postgres schema", 1)[1].split("\n## ", 1)[0]
    blocks = re.findall(r"```sql\n(.*?)```", section, flags=re.DOTALL)
    assert len(blocks) == 1, "04 §6 must contain exactly one ```sql block"
    return blocks[0]


def _migration_sql() -> str:
    spec = importlib.util.spec_from_file_location("migration_0001", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return ";\n".join(module.UPGRADE) + ";"


def _statements(sql: str) -> list[str]:
    sql = re.sub(r"--[^\n]*", "", sql)  # comments
    sql = re.sub(r"\s+", " ", sql)
    sql = re.sub(r"\s*([(),;])\s*", r"\1", sql)  # spacing around punctuation is irrelevant
    return [s for s in sql.split(";") if s.strip()]


def test_m0_6_spec_sql_matches_migration_0001() -> None:
    spec, migration = _statements(_spec_sql()), _statements(_migration_sql())
    assert spec == migration, (
        "04-data-model §6 SQL and migrations/versions/0001_initial.py differ. "
        "Never edit an applied migration: write a new revision (alembic revision -m ...) "
        "for the schema change, and update this check to cover it."
    )


def test_normalization_ignores_only_comments_and_whitespace() -> None:
    assert _statements("CREATE TABLE t (\n  a int, -- note\n  b text\n);") == [
        "CREATE TABLE t(a int,b text)"
    ]
    assert _statements("CREATE TABLE t (a int)") != _statements("CREATE TABLE t (a bigint)")
