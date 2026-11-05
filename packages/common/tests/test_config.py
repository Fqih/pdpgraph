# SPDX-License-Identifier: Apache-2.0
"""Config loader: pydantic-settings + YAML, precedence, strictness (M0.3, 09 §2)."""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError
from pydantic_settings import SettingsConfigDict

from common.config import YamlSettings


def _settings_cls(yaml_file: Path | None, env_file: Path | None = None) -> type[YamlSettings]:
    class Demo(YamlSettings):
        model_config = SettingsConfigDict(
            yaml_file=yaml_file, env_file=env_file, env_prefix="DEMO_"
        )

        name: str
        rrf_k: int = 60
        api_key: SecretStr | None = None

    return Demo


@pytest.fixture
def yaml_file(tmp_path: Path) -> Path:
    path = tmp_path / "demo.yaml"
    path.write_text("name: from-yaml\nrrf_k: 30\n")
    return path


def test_yaml_overrides_defaults(yaml_file: Path) -> None:
    s = _settings_cls(yaml_file)()
    assert (s.name, s.rrf_k) == ("from-yaml", 30)


def test_precedence_init_env_dotenv_yaml(
    yaml_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("DEMO_RRF_K=40\nDEMO_NAME=from-dotenv\nOTHER_SERVICE_KEY=ignored\n")
    cls = _settings_cls(yaml_file, dotenv)
    assert cls().rrf_k == 40  # .env beats YAML
    monkeypatch.setenv("DEMO_RRF_K", "50")
    assert cls().rrf_k == 50  # environment beats .env
    assert cls(rrf_k=70).rrf_k == 70  # explicit init beats everything


def test_missing_required_value_fails(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("{}\n")
    with pytest.raises(ValidationError):
        _settings_cls(empty)()


def test_unknown_yaml_key_fails(tmp_path: Path) -> None:
    path = tmp_path / "typo.yaml"
    path.write_text("name: x\nrrf_kk: 1\n")
    with pytest.raises(ValidationError):
        _settings_cls(path)()


def test_configured_yaml_file_must_exist(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _settings_cls(tmp_path / "missing.yaml")()


def test_no_yaml_file_uses_env_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_NAME", "env-only")
    assert _settings_cls(None)().name == "env-only"


def test_sec_11_secrets_are_not_printed(yaml_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_API_KEY", "k-very-secret")
    s = _settings_cls(yaml_file)()
    assert "k-very-secret" not in repr(s)
    assert s.api_key is not None
    assert s.api_key.get_secret_value() == "k-very-secret"
