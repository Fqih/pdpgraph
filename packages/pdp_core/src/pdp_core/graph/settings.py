# SPDX-License-Identifier: Apache-2.0
"""Neo4j connection settings: the `NEO4J_*` variables of the compose `core` profile (M0.2).

Defaults target the loopback-published store (SEC-15). The password never appears in `repr()`.
"""

from neo4j import Driver, GraphDatabase
from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict

from common.config import YamlSettings


class Neo4jSettings(YamlSettings):
    model_config = SettingsConfigDict(env_prefix="NEO4J_")

    uri: str = "bolt://127.0.0.1:7687"
    user: str = "neo4j"
    password: SecretStr


def connect(settings: Neo4jSettings | None = None) -> Driver:
    s = settings or Neo4jSettings()
    return GraphDatabase.driver(s.uri, auth=(s.user, s.password.get_secret_value()))
