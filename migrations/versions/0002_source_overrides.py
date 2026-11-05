# SPDX-License-Identifier: Apache-2.0
"""Override counts on `sources` (04 §1, §6; M1.2 safeguard).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Statements copied from 04 §6 (the "-- 0002" lines).
UPGRADE = [
    "ALTER TABLE sources ADD COLUMN overrides_total int NOT NULL DEFAULT 0",
    "ALTER TABLE sources ADD COLUMN overrides_unconfirmed int NOT NULL DEFAULT 0",
]
DOWNGRADE = [
    "ALTER TABLE sources DROP COLUMN overrides_unconfirmed",
    "ALTER TABLE sources DROP COLUMN overrides_total",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
