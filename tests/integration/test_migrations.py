# SPDX-License-Identifier: Apache-2.0
"""Alembic migrations match 04-data-model §6; upgrade is idempotent and reversible (M0.6).

Runs against a throwaway database on the `core` Postgres. Requires `make up`.
"""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, text

from common.db import PostgresSettings

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]

# 04 §6: table -> {column: (information_schema data_type, is_nullable)}.
EXPECTED: dict[str, dict[str, tuple[str, bool]]] = {
    "sources": {
        "source_id": ("text", False),
        "title": ("text", False),
        "instrument_type": ("text", False),
        "number": ("integer", True),
        "year": ("integer", True),
        "enacted_on": ("date", True),
        "promulgated_on": ("date", True),
        "effective_from": ("date", True),
        "url": ("text", True),
        "sha256": ("text", False),
        "fetched_at": ("timestamp with time zone", False),
        "parser_version": ("text", False),
    },
    "decision_traces": {
        "request_id": ("uuid", False),
        "trace_id": ("text", False),
        "kind": ("text", False),
        "created_at": ("timestamp with time zone", False),
        "request": ("jsonb", False),
        "pipeline_variant": ("text", False),
        "config_hash": ("text", False),
        "states": ("jsonb", False),
        "response": ("jsonb", True),
        "error": ("jsonb", True),
        "total_ms": ("double precision", True),
    },
    "obligation_review_queue": {
        "obligation_node_id": ("text", False),
        "candidate": ("jsonb", False),
        "status": ("text", False),
        "reviewer": ("text", True),
        "reviewed_at": ("timestamp with time zone", True),
        "note": ("text", True),
    },
    "gw_requests": {
        "request_id": ("uuid", False),
        "trace_id": ("text", True),
        "ts": ("timestamp with time zone", False),
        "tenant": ("text", False),
        "data_class": ("text", False),
        "requested_model": ("text", True),
        "task_tag": ("text", True),
        "policy_allowed_tiers": ("ARRAY", False),
        "policy_reasons": ("jsonb", True),
        "cache_result": ("text", False),
        "router_version": ("text", True),
        "router_scores": ("jsonb", True),
        "tau": ("double precision", True),
        "chosen_tier": ("text", True),
        "final_tier": ("text", True),
        "fallbacks": ("jsonb", True),
        "stream": ("boolean", False),
        "prompt_tokens": ("integer", True),
        "completion_tokens": ("integer", True),
        "tokens_estimated": ("boolean", True),
        "cost_usd": ("numeric", True),
        "ttft_ms": ("double precision", True),
        "total_ms": ("double precision", True),
        "gateway_overhead_ms": ("double precision", True),
        "status_code": ("integer", False),
        "error_code": ("text", True),
        "features_ref": ("text", True),
    },
    "eval_runs": {
        "run_id": ("uuid", False),
        "started_at": ("timestamp with time zone", False),
        "finished_at": ("timestamp with time zone", True),
        "suite": ("text", False),
        "dataset_version": ("text", False),
        "config_hash": ("text", False),
        "git_sha": ("text", False),
        "hardware_profile": ("text", True),
        "summary": ("jsonb", True),
    },
    "eval_results": {
        "run_id": ("uuid", False),
        "item_id": ("text", False),
        "variant": ("text", False),
        "output": ("jsonb", False),
        "metrics": ("jsonb", False),
        "judge": ("jsonb", True),
    },
}

PRIMARY_KEYS = {
    "sources": ["source_id"],
    "decision_traces": ["request_id"],
    "obligation_review_queue": ["obligation_node_id"],
    "gw_requests": ["request_id"],
    "eval_runs": ["run_id"],
    "eval_results": ["run_id", "item_id", "variant"],
}

INDEXES = {
    "ix_decision_traces_created_at": ("decision_traces", "(created_at DESC)"),
    "ix_gw_requests_ts": ("gw_requests", "(ts DESC)"),
    "ix_gw_requests_tenant_ts": ("gw_requests", "(tenant, ts DESC)"),
}

DEFAULTS = {
    ("decision_traces", "created_at"): "now()",
    ("obligation_review_queue", "status"): "'PENDING'::text",
    ("gw_requests", "ts"): "now()",
    ("gw_requests", "tokens_estimated"): "false",
}


@pytest.fixture
def engine() -> Iterator[Engine]:
    """A fresh, empty database for each test, dropped afterwards."""
    admin_url = PostgresSettings().url()
    name = f"pdpgraph_migtest_{uuid.uuid4().hex[:12]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    eng = create_engine(admin_url.set(database=name))
    try:
        yield eng
    finally:
        eng.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def _alembic(engine: Engine) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["url"] = engine.url
    return cfg


def _tables(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        )
        return {r[0] for r in rows}


def _schema_snapshot(engine: Engine) -> list[tuple[object, ...]]:
    with engine.connect() as conn:
        cols = conn.execute(
            text(
                "SELECT table_name, column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns WHERE table_schema='public' ORDER BY 1, 2"
            )
        ).all()
        idx = conn.execute(
            text("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY 1")
        ).all()
    return [tuple(r) for r in [*cols, *idx]]


def test_m0_6_upgrade_creates_04_schema(engine: Engine) -> None:
    command.upgrade(_alembic(engine), "head")
    assert _tables(engine) == {*EXPECTED, "alembic_version"}
    with engine.connect() as conn:
        for table, columns in EXPECTED.items():
            rows = conn.execute(
                text(
                    "SELECT column_name, data_type, is_nullable, column_default "
                    "FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=:t"
                ),
                {"t": table},
            ).all()
            actual = {r[0]: (r[1], r[2] == "YES") for r in rows}
            assert actual == columns, table
            for col, default in ((r[0], r[3]) for r in rows):
                assert default == DEFAULTS.get((table, col)), (table, col)
            pk = conn.execute(
                text(
                    "SELECT a.attname FROM pg_index i "
                    "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                    "WHERE i.indrelid = CAST(:t AS regclass) AND i.indisprimary "
                    "ORDER BY array_position(i.indkey, a.attnum)"
                ),
                {"t": table},
            ).scalars()
            assert list(pk) == PRIMARY_KEYS[table], table
        for name, (table, index_cols) in INDEXES.items():
            indexdef = conn.execute(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = :n"), {"n": name}
            ).scalar_one()
            assert indexdef.endswith(f"ON public.{table} USING btree {index_cols}"), indexdef
        fk = conn.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = 'eval_results'::regclass AND contype = 'f'"
            )
        ).scalar_one()
        assert fk == "FOREIGN KEY (run_id) REFERENCES eval_runs(run_id)"
        precision = conn.execute(
            text(
                "SELECT numeric_precision, numeric_scale FROM information_schema.columns "
                "WHERE table_name='gw_requests' AND column_name='cost_usd'"
            )
        ).one()
        assert tuple(precision) == (12, 6)


def test_m0_6_upgrade_is_idempotent(engine: Engine) -> None:
    cfg = _alembic(engine)
    command.upgrade(cfg, "head")
    before = _schema_snapshot(engine)
    command.upgrade(cfg, "head")
    assert _schema_snapshot(engine) == before
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == head


def test_m0_6_downgrade_then_reupgrade(engine: Engine) -> None:
    cfg = _alembic(engine)
    command.upgrade(cfg, "head")
    before = _schema_snapshot(engine)
    command.downgrade(cfg, "base")
    assert _tables(engine) == {"alembic_version"}
    command.upgrade(cfg, "head")
    assert _schema_snapshot(engine) == before
