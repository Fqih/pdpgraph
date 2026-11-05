# SPDX-License-Identifier: Apache-2.0
"""The service never downloads; downloads are explicit and pinned (M0.4)."""

from pathlib import Path
from typing import Any

import pytest

from models_aux import __main__ as main
from models_aux import download, models
from models_aux.settings import ModelsAuxSettings


def test_service_refuses_to_start_without_offline_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    with pytest.raises(SystemExit, match="HF_HUB_OFFLINE=1"):
        main.require_offline()
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    with pytest.raises(SystemExit, match="HF_HUB_OFFLINE=1"):
        main.require_offline()
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    main.require_offline()


def test_loader_uses_local_files_and_pinned_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []

    def fake(repo: str, **kw: Any) -> None:
        seen.append({"repo": repo, **kw})
        raise OSError("stop")

    monkeypatch.setattr(models.AutoTokenizer, "from_pretrained", fake)
    settings = ModelsAuxSettings()
    with pytest.raises(SystemExit, match="make models-download"):
        models.load_models(settings)
    (call,) = seen
    assert call["local_files_only"] is True
    assert call["revision"] == settings.models["embed"].revision
    assert call["cache_dir"] == settings.cache_dir


def test_download_is_pinned_and_filtered(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(download, "snapshot_download", lambda **kw: seen.append(kw) or "")
    settings = ModelsAuxSettings(cache_dir=tmp_path)
    download.download_all(settings)
    assert [c["repo_id"] for c in seen] == [s.repo for s in settings.models.values()]
    for call, spec in zip(seen, settings.models.values(), strict=True):
        assert call["revision"] == spec.revision
        assert call["allow_patterns"] == spec.allow_patterns
        assert call["cache_dir"] == tmp_path


def test_model_weights_load_from_safetensors_only(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []

    def fake_model(repo: str, **kw: Any) -> None:
        seen.append(kw)
        raise OSError("stop")

    monkeypatch.setattr(models.AutoTokenizer, "from_pretrained", lambda *a, **kw: object())
    monkeypatch.setattr(models.AutoModel, "from_pretrained", fake_model)
    with pytest.raises(SystemExit):
        models.load_models(ModelsAuxSettings())
    (call,) = seen
    assert call["use_safetensors"] is True
    assert call["local_files_only"] is True
