# SPDX-License-Identifier: Apache-2.0
"""Initial schema: PDPGraph, Tierline, and eval tables exactly as 04-data-model §6 (M0.6).

Revision ID: 0001
Revises:
Create Date: 2026-11-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Statements copied from 04 §6; keep them identical when the spec changes (new revision).
UPGRADE = [
    # PDPGraph
    """
    CREATE TABLE sources (
      source_id text PRIMARY KEY, title text NOT NULL, instrument_type text NOT NULL,
      number int, year int, enacted_on date, promulgated_on date, effective_from date,
      url text, sha256 text NOT NULL, fetched_at timestamptz NOT NULL,
      parser_version text NOT NULL
    )
    """,
    """
    CREATE TABLE decision_traces (
      request_id uuid PRIMARY KEY,
      trace_id text NOT NULL,
      kind text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      request jsonb NOT NULL,
      pipeline_variant text NOT NULL,
      config_hash text NOT NULL,
      states jsonb NOT NULL,
      response jsonb,
      error jsonb,
      total_ms double precision
    )
    """,
    "CREATE INDEX ix_decision_traces_created_at ON decision_traces (created_at DESC)",
    """
    CREATE TABLE obligation_review_queue (
      obligation_node_id text PRIMARY KEY, candidate jsonb NOT NULL,
      status text NOT NULL DEFAULT 'PENDING', reviewer text, reviewed_at timestamptz, note text
    )
    """,
    # Tierline
    """
    CREATE TABLE gw_requests (
      request_id uuid PRIMARY KEY,
      trace_id text,
      ts timestamptz NOT NULL DEFAULT now(),
      tenant text NOT NULL,
      data_class text NOT NULL,
      requested_model text,
      task_tag text,
      policy_allowed_tiers text[] NOT NULL,
      policy_reasons jsonb,
      cache_result text NOT NULL,
      router_version text,
      router_scores jsonb,
      tau double precision,
      chosen_tier text,
      final_tier text,
      fallbacks jsonb,
      stream boolean NOT NULL,
      prompt_tokens int, completion_tokens int, tokens_estimated boolean DEFAULT false,
      cost_usd numeric(12,6),
      ttft_ms double precision, total_ms double precision, gateway_overhead_ms double precision,
      status_code int NOT NULL,
      error_code text,
      features_ref text
    )
    """,
    "CREATE INDEX ix_gw_requests_ts ON gw_requests (ts DESC)",
    "CREATE INDEX ix_gw_requests_tenant_ts ON gw_requests (tenant, ts DESC)",
    # Evals
    """
    CREATE TABLE eval_runs (
      run_id uuid PRIMARY KEY, started_at timestamptz NOT NULL, finished_at timestamptz,
      suite text NOT NULL, dataset_version text NOT NULL, config_hash text NOT NULL,
      git_sha text NOT NULL, hardware_profile text, summary jsonb
    )
    """,
    """
    CREATE TABLE eval_results (
      run_id uuid REFERENCES eval_runs, item_id text NOT NULL, variant text NOT NULL,
      output jsonb NOT NULL, metrics jsonb NOT NULL, judge jsonb,
      PRIMARY KEY (run_id, item_id, variant)
    )
    """,
]

# Reverse dependency order; indexes go with their tables.
TABLES = [
    "eval_results",
    "eval_runs",
    "gw_requests",
    "obligation_review_queue",
    "decision_traces",
    "sources",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE {table}")
