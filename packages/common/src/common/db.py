# SPDX-License-Identifier: Apache-2.0
"""Postgres connection settings (04-data-model §6).

Reads the same `POSTGRES_*` variables as the compose `core` profile, so one `.env` serves both.
Defaults target the loopback-published store (SEC-15). The password is a secret: it is never
included in `repr()` or in the rendered URL string.
"""

from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict
from sqlalchemy import URL

from common.config import YamlSettings


class PostgresSettings(YamlSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_")

    host: str = "127.0.0.1"
    port: int = 5432
    user: str = "pdpgraph"
    db: str = "pdpgraph"
    password: SecretStr

    def url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.db,
        )
