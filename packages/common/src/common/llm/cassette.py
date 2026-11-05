# SPDX-License-Identifier: Apache-2.0
"""Cassette keys and store for LLM replay (06 §7, NFR-06).

The key is SHA-256 over a canonical JSON of the fields that determine the output: model,
messages (role and content only), sampling params, response_format (schema replaced by its
hash), prompt version, and attempt number. Volatile fields (trace/request ids, timestamps,
headers) are never part of it. One JSON file per key under `<dir>/<namespace>/<key>.json`.

The writer refuses `pii` (by data class or by `common.pii` on any string in the entry) and any
entry containing a configured secret value (upstream host, key), then applies the logging
sanitizer before writing.
"""

import hashlib
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from common.llm.errors import CassetteWriteRefusedError
from common.llm.settings import DataClass
from common.logging import redact
from common.pii import contains_pii

_NAMESPACE_RE = re.compile(r"[a-z0-9][a-z0-9._-]*")
_KEY_RE = re.compile(r"[0-9a-f]{64}")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _float(value: float | None) -> float | None:
    return None if value is None else float(value)


def _hash_schema(response_format: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if response_format is None:
        return None
    out = dict(response_format)
    js = out.get("json_schema")
    if isinstance(js, Mapping) and "schema" in js:
        out["json_schema"] = {k: v for k, v in js.items() if k != "schema"} | {
            "schema_sha256": _sha256(js["schema"])
        }
    return out


def canonical_request(
    *,
    model: str,
    messages: Sequence[Mapping[str, str]],
    temperature: float | None,
    top_p: float | None,
    max_tokens: int | None,
    seed: int | None,
    stop: Sequence[str] | None,
    response_format: Mapping[str, Any] | None,
    prompt_version: str | None,
    attempt: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "temperature": _float(temperature),
        "top_p": _float(top_p),
        "max_tokens": max_tokens,
        "seed": seed,
        "stop": list(stop) if stop is not None else None,
        "response_format": _hash_schema(response_format),
        "prompt_version": prompt_version,
        "attempt": attempt,
    }


def cassette_key(canonical: Mapping[str, Any]) -> str:
    return _sha256(canonical)


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from _strings(v)


def check_recordable(data_class: DataClass, *values: Any) -> None:
    """Raise if a request/response with this data class and content may not be recorded."""
    if data_class is DataClass.PII:
        raise CassetteWriteRefusedError("refusing to record a call with data_class=pii")
    if any(contains_pii(s) for v in values for s in _strings(v)):
        raise CassetteWriteRefusedError("refusing to record: content matches a PII pattern")


class CassetteStore:
    def __init__(self, root: Path, namespace: str, *, secrets: Sequence[str] = ()) -> None:
        if not _NAMESPACE_RE.fullmatch(namespace):
            raise ValueError(f"invalid cassette namespace: {namespace!r}")
        self.dir = root / namespace
        self._secrets = tuple(s for s in secrets if s)

    def _path(self, key: str) -> Path:
        if not _KEY_RE.fullmatch(key):
            raise ValueError("cassette key must be 64 lowercase hex characters")
        return self.dir / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path(key)
        if not path.is_file():
            return None
        entry: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return entry

    def put(
        self,
        *,
        request: Mapping[str, Any],
        data_class: DataClass,
        task_tag: str | None,
        response: Mapping[str, Any],
        latency_ms: float,
    ) -> Path:
        key = cassette_key(request)
        entry = {
            "key": key,
            "request": request,
            "data_class": str(data_class),
            "task_tag": task_tag,
            "response": response,
            "usage": response.get("usage"),
            "latency_ms": latency_ms,
            "model": response.get("model"),
            "recorded_at": datetime.now(UTC).isoformat(),
            "client_version": f"pdpgraph-common/{version('pdpgraph-common')}",
        }
        self._refuse_secrets(_canonical_json(entry))
        check_recordable(data_class, request, response)
        text = json.dumps(
            redact(entry, self._secrets), indent=2, sort_keys=True, ensure_ascii=False
        )
        self._refuse_secrets(text)
        path = self._path(key)
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text + "\n", encoding="utf-8")
        tmp.replace(path)
        return path

    def _refuse_secrets(self, text: str) -> None:
        lowered = text.lower()
        if any(s.lower() in lowered for s in self._secrets):
            raise CassetteWriteRefusedError(
                "refusing to record: entry contains a configured secret"
            )
