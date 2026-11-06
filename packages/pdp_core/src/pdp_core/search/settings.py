# SPDX-License-Identifier: Apache-2.0
"""Search endpoints (M1.6): OpenSearch and models-aux, loopback by default (SEC-15)."""

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from common.config import YamlSettings


class SearchSettings(YamlSettings):
    model_config = SettingsConfigDict(env_prefix="SEARCH_")

    opensearch_url: str = "http://127.0.0.1:9200"
    models_aux_url: str = "http://127.0.0.1:8070"
    index_retention: int = Field(default=2, ge=1)  # builds kept: live + previous (rollback)
