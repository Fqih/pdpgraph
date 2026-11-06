# SPDX-License-Identifier: Apache-2.0
"""bge-m3 ColBERT head (`colbert_linear.pt`) read without unpickling (M1.6, ADR-020, SEC-13).

The head is a `torch.save` zip of one `Linear(dim, dim)` state dict. Nothing in it is executed:

1. the file's SHA-256 must equal the pinned value (configs/models_aux.yaml);
2. `data.pkl` is only disassembled (`pickletools.genops`, no execution) and every global it
   names must be in `_ALLOWED`;
3. the raw tensor storages are read from the zip; with the dim known, the weight is the
   storage of dim*dim elements and the bias the one of dim elements.
"""

import hashlib
import pickletools
import zipfile
from pathlib import Path

import torch

_ALLOWED = {
    ("collections", "OrderedDict"),
    ("torch._utils", "_rebuild_tensor_v2"),
    ("torch", "HalfStorage"),
    ("torch", "FloatStorage"),
}
_DTYPES = {"HalfStorage": torch.float16, "FloatStorage": torch.float32}
_STRINGS = {"SHORT_BINUNICODE", "BINUNICODE", "UNICODE", "SHORT_BINSTRING", "BINSTRING"}


class ColbertError(Exception):
    """The head file is not the pinned, plain Linear state dict."""


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


def read_linear(path: Path, sha256: str, *, dim: int) -> tuple[torch.Tensor, torch.Tensor]:
    """(weight [dim, dim], bias [dim]) as float32."""
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != sha256:
        raise ColbertError(f"{path.name}: sha256 {actual} is not the pinned {sha256}")
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        pkl_name = next((n for n in names if n.endswith("/data.pkl")), None)
        if pkl_name is None:
            raise ColbertError(f"{path.name}: no data.pkl")
        prefix = pkl_name.removesuffix("data.pkl")
        named = _globals(z.read(pkl_name))
        if bad := sorted(named - _ALLOWED):
            raise ColbertError(f"{path.name}: unexpected globals {' '.join(map(' '.join, bad))}")
        if prefix + "byteorder" in names and z.read(prefix + "byteorder") != b"little":
            raise ColbertError(f"{path.name}: not little-endian")
        dtypes = {_DTYPES[n] for m, n in named if m == "torch" and n in _DTYPES}
        if len(dtypes) != 1:
            raise ColbertError(f"{path.name}: expected one storage dtype, got {dtypes}")
        (dtype,) = dtypes
        size = torch.empty((), dtype=dtype).element_size()
        storages = [z.read(n) for n in names if n.startswith(prefix + "data/")]
    by_size = {len(s): s for s in storages}
    weight, bias = by_size.get(dim * dim * size), by_size.get(dim * size)
    if len(storages) != 2 or weight is None or bias is None:
        sizes = sorted(len(s) for s in storages)
        raise ColbertError(f"{path.name}: storage sizes {sizes} do not fit Linear({dim}, {dim})")
    w = torch.frombuffer(bytearray(weight), dtype=dtype).reshape(dim, dim).float()
    b = torch.frombuffer(bytearray(bias), dtype=dtype).float()
    return w, b
