# SPDX-License-Identifier: Apache-2.0
"""Download-time conversion of pickled weight files to safetensors (M1.6, ADR-020, SEC-13).

Some heads exist only as `torch.save` pickles (bge-m3 `colbert_linear.pt`). `make
models-download` converts them once; the service only ever loads the safetensors output.

1. the source file's SHA-256 must equal the pinned value (configs/models_aux.yaml `convert`);
2. pre-check: `data.pkl` is disassembled (`pickletools.genops`, nothing executed) and every
   global it names must be in `_ALLOWED`;
3. `torch.load(weights_only=True)`, then `safetensors.torch.save_file`; the caller compares
   the output's SHA-256 with the pinned `output_sha256`.
"""

import hashlib
import pickletools
import zipfile
from pathlib import Path

import torch
from safetensors.torch import save_file

_ALLOWED = {
    ("collections", "OrderedDict"),
    ("torch._utils", "_rebuild_tensor_v2"),
    ("torch", "HalfStorage"),
    ("torch", "FloatStorage"),
}
_STRINGS = {"SHORT_BINUNICODE", "BINUNICODE", "UNICODE", "SHORT_BINSTRING", "BINSTRING"}


class ConvertError(Exception):
    """The file is not the pinned, plain tensor state dict."""


def converted_dir(cache_dir: Path, repo: str, revision: str) -> Path:
    return cache_dir / "converted" / f"{repo.replace('/', '--')}@{revision}"


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _globals(pkl: bytes) -> set[tuple[str, str]]:
    """Globals named by a pickle, found by disassembly only."""
    found: set[tuple[str, str]] = set()
    stack: list[object] = []  # pushed values, strings only (enough for STACK_GLOBAL)
    memo: dict[int, object] = {}
    for op, arg, _ in pickletools.genops(pkl):
        if op.name == "GLOBAL":
            module, name = str(arg).split(" ", 1)
            found.add((module, name))
        elif op.name == "STACK_GLOBAL":
            found.add((str(stack[-2]), str(stack[-1])))
        elif op.name == "MEMOIZE":
            memo[len(memo)] = stack[-1] if stack else None
            continue  # MEMOIZE pushes nothing
        elif op.name in {"BINPUT", "LONG_BINPUT", "PUT"}:
            memo[int(arg)] = stack[-1] if stack else None  # type: ignore[arg-type]
            continue
        elif op.name in {"BINGET", "LONG_BINGET", "GET"}:
            stack.append(memo.get(int(arg)))  # type: ignore[arg-type]
            continue
        stack.append(arg if op.name in _STRINGS else None)
    return found


def scan_pickle(path: Path) -> None:
    """Refuse a torch zip whose pickle names any global outside the allowlist."""
    with zipfile.ZipFile(path) as z:
        pkl = next((n for n in z.namelist() if n.endswith("/data.pkl")), None)
        if pkl is None:
            raise ConvertError(f"{path.name}: no data.pkl")
        named = _globals(z.read(pkl))
    if bad := sorted(named - _ALLOWED):
        raise ConvertError(f"{path.name}: unexpected globals {' '.join(map(' '.join, bad))}")


def convert_to_safetensors(src: Path, sha256: str, dst: Path) -> str:
    """Convert a pinned pickled state dict; returns the SHA-256 of the safetensors output."""
    actual = sha256_of(src)
    if actual != sha256:
        raise ConvertError(f"{src.name}: sha256 {actual} is not the pinned {sha256}")
    scan_pickle(src)
    state = torch.load(src, weights_only=True, map_location="cpu")
    if not isinstance(state, dict) or not all(isinstance(v, torch.Tensor) for v in state.values()):
        raise ConvertError(f"{src.name}: not a tensor state dict")
    dst.parent.mkdir(parents=True, exist_ok=True)
    save_file({k: v.contiguous() for k, v in state.items()}, dst)
    return sha256_of(dst)
