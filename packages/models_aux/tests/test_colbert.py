# SPDX-License-Identifier: Apache-2.0
"""bge-m3 ColBERT head read without unpickling (M1.6, ADR-020, SEC-13)."""

import hashlib
import io
import pickle
import zipfile
from pathlib import Path

import pytest
import torch

from models_aux.colbert import ColbertError, read_linear

DIM = 8


def _save(path: Path, state: dict[str, torch.Tensor]) -> str:
    torch.save(state, path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _linear() -> dict[str, torch.Tensor]:
    torch.manual_seed(0)
    lin = torch.nn.Linear(DIM, DIM).half()
    return {"weight": lin.weight.detach().clone(), "bias": lin.bias.detach().clone()}


def test_reads_fp16_linear_state_dict(tmp_path: Path) -> None:
    state = _linear()
    path = tmp_path / "colbert_linear.pt"
    sha = _save(path, state)
    weight, bias = read_linear(path, sha, dim=DIM)
    assert weight.dtype == bias.dtype == torch.float32
    assert torch.equal(weight, state["weight"].float())
    assert torch.equal(bias, state["bias"].float())


def test_hash_mismatch_is_refused_before_reading(tmp_path: Path) -> None:
    path = tmp_path / "colbert_linear.pt"
    _save(path, _linear())
    with pytest.raises(ColbertError, match="sha256"):
        read_linear(path, "0" * 64, dim=DIM)


class _Evil:
    def __reduce__(self) -> tuple[object, tuple[str]]:
        return (print, ("pwned",))


def test_unexpected_pickle_globals_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "colbert_linear.pt"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("archive/data.pkl", pickle.dumps({"weight": _Evil()}))
    path.write_bytes(buf.getvalue())
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ColbertError, match="builtins print"):
        read_linear(path, sha, dim=DIM)


def test_wrong_shape_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "colbert_linear.pt"
    sha = _save(path, _linear())
    with pytest.raises(ColbertError, match="storage"):
        read_linear(path, sha, dim=DIM * 2)
