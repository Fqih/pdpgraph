# SPDX-License-Identifier: Apache-2.0
"""Settings base: pydantic-settings with a YAML file source (09 §2, 04 §8).

Precedence, highest first: explicit init kwargs > environment > `.env` > YAML > field defaults.
Unknown keys in YAML are errors (catches typos in tuned values). A configured YAML file that
does not exist is an error, so a service never silently runs on defaults. Unrelated `.env`
entries are ignored, so services with different prefixes can share one `.env`.
"""

from pathlib import Path
from typing import Any

from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class _KnownFieldsOnly(PydanticBaseSettingsSource):
    """Wraps the `.env` source and drops keys that are not fields of this settings class."""

    def __init__(self, settings_cls: type[BaseSettings], inner: PydanticBaseSettingsSource):
        super().__init__(settings_cls)
        self._inner = inner

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return self._inner.get_field_value(field, field_name)

    def __call__(self) -> dict[str, Any]:
        fields = self.settings_cls.model_fields
        return {k: v for k, v in self._inner().items() if k in fields}


class YamlSettings(BaseSettings):
    """Subclass and set `yaml_file`, `env_prefix` (and optionally `env_file`) in model_config."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        frozen=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_file = settings_cls.model_config.get("yaml_file")
        sources: tuple[PydanticBaseSettingsSource, ...] = (
            init_settings,
            env_settings,
            _KnownFieldsOnly(settings_cls, dotenv_settings),
        )
        if yaml_file is not None:
            if not Path(str(yaml_file)).is_file():
                raise FileNotFoundError(f"settings file not found: {yaml_file}")
            sources += (YamlConfigSettingsSource(settings_cls),)
        return (*sources, file_secret_settings)
