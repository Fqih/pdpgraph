# SPDX-License-Identifier: Apache-2.0
"""Cassette keys and the cassette writer guards (M0.5, NFR-06)."""

import json
from pathlib import Path
from typing import Any

import pytest

from common.llm import (
    CassetteStore,
    CassetteWriteRefusedError,
    DataClass,
    canonical_request,
    cassette_key,
)

MESSAGES = [
    {"role": "system", "content": "Jawab singkat."},
    {"role": "user", "content": "Apa itu?"},
]
SCHEMA_RF = {
    "type": "json_schema",
    "json_schema": {"name": "Answer", "strict": True, "schema": {"type": "object"}},
}


def _canon(**overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": "m1",
        "messages": MESSAGES,
        "temperature": 0.0,
        "top_p": None,
        "max_tokens": 256,
        "seed": 7,
        "stop": None,
        "response_format": SCHEMA_RF,
        "prompt_version": "plan-v1",
        "attempt": 1,
    }
    params.update(overrides)
    return canonical_request(**params)


def test_canonical_form_has_exactly_the_key_fields() -> None:
    assert set(_canon()) == {
        "model",
        "messages",
        "temperature",
        "top_p",
        "max_tokens",
        "seed",
        "stop",
        "response_format",
        "prompt_version",
        "attempt",
    }


def test_schema_is_hashed_not_embedded() -> None:
    rf = _canon()["response_format"]
    assert "schema" not in rf["json_schema"]
    assert len(rf["json_schema"]["schema_sha256"]) == 64


def test_key_is_stable_across_dict_order_and_int_float() -> None:
    reordered = [{"content": m["content"], "role": m["role"]} for m in MESSAGES]
    assert cassette_key(_canon()) == cassette_key(_canon(messages=reordered, temperature=0))
    assert len(cassette_key(_canon())) == 64


@pytest.mark.parametrize(
    "override",
    [
        {"model": "m2"},
        {"messages": [{"role": "user", "content": "lain"}]},
        {"temperature": 0.2},
        {"top_p": 0.9},
        {"max_tokens": 512},
        {"seed": 8},
        {"stop": ["\n"]},
        {"response_format": None},
        {
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "Answer", "strict": True, "schema": {"type": "array"}},
            }
        },
        {"prompt_version": "plan-v2"},
        {"attempt": 2},
    ],
)
def test_every_key_field_changes_the_key(override: dict[str, Any]) -> None:
    assert cassette_key(_canon(**override)) != cassette_key(_canon())


def test_messages_keep_only_role_and_content() -> None:
    msgs = [{"role": "user", "content": "x", "request_id": "r-1", "ts": "2026-11-05"}]
    assert _canon(messages=msgs)["messages"] == [{"role": "user", "content": "x"}]


# --- writer -----------------------------------------------------------------------------------

SECRETS = ("vps.example.internal", "sk-test-0123456789abcdef")


def _store(tmp_path: Path) -> CassetteStore:
    return CassetteStore(tmp_path, "unit", secrets=SECRETS)


def _body(content: str = '{"ok": true}', model: str = "m1-2026") -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15},
    }


def _put(store: CassetteStore, request: dict[str, Any] | None = None, **kw: Any) -> Path:
    args: dict[str, Any] = {
        "request": request or _canon(),
        "data_class": DataClass.PUBLIC,
        "task_tag": "pdp.extract",
        "response": _body(),
        "latency_ms": 12.5,
    }
    args.update(kw)
    return store.put(**args)


def test_put_writes_one_json_file_per_key(tmp_path: Path) -> None:
    store = _store(tmp_path)
    path = _put(store)
    key = cassette_key(_canon())
    assert path == tmp_path / "unit" / f"{key}.json"
    entry = json.loads(path.read_text(encoding="utf-8"))
    assert entry["key"] == key
    assert entry["request"] == _canon()
    assert entry["response"] == _body()
    assert entry["usage"] == {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15}
    assert entry["latency_ms"] == 12.5
    assert entry["model"] == "m1-2026"
    assert entry["data_class"] == "public"
    assert entry["task_tag"] == "pdp.extract"
    assert entry["recorded_at"].endswith("+00:00")
    assert entry["client_version"].startswith("pdpgraph-common/")
    assert store.get(key) == entry


def test_get_miss_returns_none(tmp_path: Path) -> None:
    assert _store(tmp_path).get("0" * 64) is None


def test_refuses_pii_data_class(tmp_path: Path) -> None:
    with pytest.raises(CassetteWriteRefusedError, match="pii"):
        _put(_store(tmp_path), data_class=DataClass.PII)
    assert not (tmp_path / "unit").exists()


def test_refuses_pii_in_request(tmp_path: Path) -> None:
    req = _canon(messages=[{"role": "user", "content": "NIK saya 3171012345678901"}])
    with pytest.raises(CassetteWriteRefusedError, match="PII"):
        _put(_store(tmp_path), request=req)


def test_refuses_pii_in_response(tmp_path: Path) -> None:
    with pytest.raises(CassetteWriteRefusedError, match="PII"):
        _put(_store(tmp_path), response=_body("hubungi budi@example.com"))


@pytest.mark.parametrize("secret", SECRETS)
def test_refuses_configured_secret_anywhere(tmp_path: Path, secret: str) -> None:
    with pytest.raises(CassetteWriteRefusedError, match="secret") as exc:
        _put(_store(tmp_path), response=_body(model=f"proxy@{secret.upper()}"))
    assert secret not in str(exc.value)
    assert not (tmp_path / "unit").exists()


def test_writer_runs_the_logging_sanitizer(tmp_path: Path) -> None:
    path = _put(_store(tmp_path), response=_body("pakai header Bearer abc.def-123"))
    text = path.read_text(encoding="utf-8")
    assert "abc.def-123" not in text
    assert "[REDACTED]" in text


@pytest.mark.parametrize("namespace", ["", "../x", "a/b", "UPPER", ".hidden"])
def test_namespace_must_be_a_plain_name(tmp_path: Path, namespace: str) -> None:
    with pytest.raises(ValueError, match="namespace"):
        CassetteStore(tmp_path, namespace)


def test_get_rejects_malformed_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="key"):
        _store(tmp_path).get("../../etc/passwd")
