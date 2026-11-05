# SPDX-License-Identifier: Apache-2.0
"""Alembic environment. Migrations are hand-written SQL (04 §6 is normative); no ORM metadata.

The URL comes from `config.attributes["url"]` when set programmatically (tests), otherwise from
`PostgresSettings` (POSTGRES_* in `.env`). It is never written to alembic.ini.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import URL, create_engine
from sqlalchemy.pool import NullPool

from common.db import PostgresSettings

config = context.config
if config.config_file_name is not None and "url" not in config.attributes:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _url() -> URL:
    url = config.attributes.get("url")
    return url if isinstance(url, URL) else PostgresSettings().url()


if context.is_offline_mode():
    # `alembic upgrade head --sql` renders SQL for review; only the dialect is needed.
    context.configure(dialect_name="postgresql", literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(_url(), poolclass=NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, transaction_per_migration=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
