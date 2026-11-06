# SPDX-License-Identifier: Apache-2.0
"""Pickled head files: converted to safetensors at download time, never loaded at runtime
(M1.6, ADR-020, SEC-13)."""

import hashlib
import io
import pickle
import zipfile
from pathlib import Path

import pytest
import torch

from models_aux.convert import ConvertError, convert_to_safetensors, converted_dir
from models_aux.models import COLBERT_FILE, _colbert_head, load_safetensors
from models_aux.settings import ModelsAuxSettings, ModelSpec

DIM = 8


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pt(tmp_path: Path) -> tuple[Path, dict[str, torch.Tensor]]:
    torch.manual_seed(0)
    lin = torch.nn.Linear(DIM, DIM).half()
    state = {"weight": lin.weight.detach().clone(), "bias": lin.bias.detach().clone()}
    path = tmp_path / "colbert_linear.pt"
    torch.save(state, path)
    return path, state


def test_converts_to_identical_safetensors(tmp_path: Path) -> None:
    src, state = _pt(tmp_path)
    dst = tmp_path / "out" / "colbert_linear.safetensors"
    digest = convert_to_safetensors(src, _sha(src), dst)
    assert digest == _sha(dst)
    loaded = load_safetensors(dst, digest)
    assert set(loaded) == {"weight", "bias"}
    assert all(torch.equal(loaded[k], state[k]) for k in state)
    assert convert_to_safetensors(src, _sha(src), dst) == digest  # deterministic output


def test_source_hash_mismatch_is_refused_before_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src, _ = _pt(tmp_path)
    monkeypatch.setattr(torch, "load", lambda *a, **k: pytest.fail("torch.load called"))
    with pytest.raises(ConvertError, match="sha256"):
        convert_to_safetensors(src, "0" * 64, tmp_path / "x.safetensors")


class _Evil:
    def __reduce__(self) -> tuple[object, tuple[str]]:
        return (print, ("pwned",))


def test_unexpected_globals_are_refused_before_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "colbert_linear.pt"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("archive/data.pkl", pickle.dumps({"weight": _Evil()}))
    src.write_bytes(buf.getvalue())
    monkeypatch.setattr(torch, "load", lambda *a, **k: pytest.fail("torch.load called"))
    with pytest.raises(ConvertError, match="builtins print"):
        convert_to_safetensors(src, _sha(src), tmp_path / "x.safetensors")


@pytest.mark.parametrize("name", ["head.pt", "head.pth", "pytorch_model.bin", "state.pkl"])
def test_runtime_rejects_pickled_paths(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    path.write_bytes(b"\x80\x04N.")
    with pytest.raises(ValueError, match="pickle"):
        load_safetensors(path, _sha(path))


def test_runtime_checks_the_pinned_hash(tmp_path: Path) -> None:
    src, _ = _pt(tmp_path)
    dst = tmp_path / "colbert_linear.safetensors"
    convert_to_safetensors(src, _sha(src), dst)
    with pytest.raises(ValueError, match="sha256"):
        load_safetensors(dst, "0" * 64)


def test_runtime_head_never_loads_a_pickle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src, state = _pt(tmp_path)
    spec = ModelSpec(
        repo="x/y",
        revision="a" * 40,
        license="MIT",
        max_length=8,
        allow_patterns=["model.safetensors", COLBERT_FILE],
        convert={
            COLBERT_FILE: {
                "sha256": _sha(src),
                "output": "colbert_linear.safetensors",
                "output_sha256": "0" * 64,
            }
        },
    )
    out = converted_dir(tmp_path, spec.repo, spec.revision) / "colbert_linear.safetensors"
    digest = convert_to_safetensors(src, _sha(src), out)
    spec = spec.model_copy(
        update={
            "convert": {
                COLBERT_FILE: spec.convert[COLBERT_FILE].model_copy(
                    update={"output_sha256": digest}
                )
            }
        }
    )
    src.unlink()  # the pickle is gone; runtime must not need it
    monkeypatch.setattr(torch, "load", lambda *a, **k: pytest.fail("torch.load at runtime"))
    head = _colbert_head(spec, ModelsAuxSettings(cache_dir=tmp_path), DIM)
    assert torch.equal(head.weight, state["weight"].float())
