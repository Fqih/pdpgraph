# SPDX-License-Identifier: Apache-2.0
"""LLMClient against a fake OpenAI-compatible server (M0.5, FR-PDP-11, FR-PDP-18, ADR-015)."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel, ValidationError

from common.llm import (
    CassetteMissError,
    CassetteWriteRefusedError,
    DataClass,
    LLMClient,
    LLMHTTPError,
    LLMSettings,
    OutputValidationError,
    UsageLimiter,
    UsageLimitExceededError,
)
from common.telemetry import setup_tracing

pytestmark = pytest.mark.usefixtures("no_network")

BASE = "https://upstream.invalid/v1"
KEY = "sk-test-" + "0" * 16  # synthetic; built at runtime so secret scanners skip it
URL = f"{BASE}/chat/completions"
MESSAGES = [{"role": "user", "content": "Apa kewajiban pengendali data?"}]


class Answer(BaseModel):
    verdict: str
    confidence: float


def _reply(content: str, *, model: str = "m1-2026", tokens: int = 15) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-x",
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": tokens - 5, "completion_tokens": 5, "total_tokens": tokens},
        },
    )


def _settings(tmp_path: Path, **kw: Any) -> LLMSettings:
    args: dict[str, Any] = {
        "mode": "live",
        "base_url": BASE,
        "api_key": KEY,
        "model": "m1",
        "cassette_dir": tmp_path,
        "cassette_namespace": "unit",
    }
    args.update(kw)
    return LLMSettings(**args)


@pytest.fixture
def spans() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    return setup_tracing("test", exporter=exporter, set_global=False), exporter


@pytest.fixture
def mock() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        yield router


def _body(call: Any) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(call.request.content)
    return body


# --- settings ---------------------------------------------------------------------------------


def test_mode_defaults_to_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_MODE", raising=False)
    assert LLMSettings(model="m1", cassette_dir=tmp_path).mode == "replay"


@pytest.mark.parametrize("mode", ["record", "live"])
def test_upstream_modes_need_base_url(tmp_path: Path, mode: str) -> None:
    with pytest.raises(ValidationError, match="base_url"):
        LLMSettings(mode=mode, model="m1", cassette_dir=tmp_path)


@pytest.mark.parametrize("name", ["Authorization", "x-data-class", "X-Tierline-Task"])
def test_extra_headers_cannot_override_reserved(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValidationError, match="reserved"):
        _settings(tmp_path, extra_headers={name: "x"})


def test_secret_values_cover_host_and_key(tmp_path: Path) -> None:
    secrets = _settings(tmp_path, base_url="http://10.0.0.7:20128/v1").secret_values()
    assert {"10.0.0.7", "10.0.0.7:20128", KEY} <= set(secrets)


# --- headers and data class -------------------------------------------------------------------


async def test_sends_data_class_task_auth_and_extra_headers(
    tmp_path: Path, mock: respx.MockRouter
) -> None:
    route = mock.post(URL).mock(return_value=_reply("ok"))
    settings = _settings(tmp_path, extra_headers={"X-9Router-Token-Saver": "off"})
    async with LLMClient(settings) as client:
        result = await client.complete(MESSAGES, data_class=DataClass.INTERNAL, task_tag="pdp.plan")
    assert result.content == "ok"
    assert result.model == "m1-2026"
    assert result.usage.total_tokens == 15
    headers = route.calls.last.request.headers
    assert headers["x-data-class"] == "internal"
    assert headers["x-tierline-task"] == "pdp.plan"
    assert headers["authorization"] == f"Bearer {KEY}"
    assert headers["x-9router-token-saver"] == "off"
    body = _body(route.calls.last)
    assert body["model"] == "m1"
    assert body["stream"] is False
    assert body["temperature"] == 0.0


async def test_task_header_omitted_when_no_tag(tmp_path: Path, mock: respx.MockRouter) -> None:
    route = mock.post(URL).mock(return_value=_reply("ok"))
    async with LLMClient(_settings(tmp_path)) as client:
        await client.complete(MESSAGES, data_class=DataClass.PUBLIC)
    assert "x-tierline-task" not in route.calls.last.request.headers


async def test_data_class_is_required(tmp_path: Path) -> None:
    async with LLMClient(_settings(tmp_path)) as client:
        with pytest.raises(TypeError, match="data_class"):
            await client.complete(MESSAGES)  # type: ignore[call-arg]
        with pytest.raises(ValueError, match="secret"):
            await client.complete(MESSAGES, data_class="secret")  # type: ignore[arg-type]


async def test_timeouts_come_from_settings(tmp_path: Path) -> None:
    settings = _settings(tmp_path, connect_timeout_s=2.5, read_timeout_s=30.0)
    async with LLMClient(settings) as client:
        timeout = client.timeout
    assert (timeout.connect, timeout.read) == (2.5, 30.0)


async def test_http_error_hides_host_and_body(tmp_path: Path, mock: respx.MockRouter) -> None:
    mock.post(URL).mock(return_value=httpx.Response(503, text="upstream.invalid overloaded"))
    async with LLMClient(_settings(tmp_path)) as client:
        with pytest.raises(LLMHTTPError, match="503") as exc:
            await client.complete(MESSAGES, data_class=DataClass.PUBLIC)
    assert "upstream.invalid" not in str(exc.value)


async def test_transport_error_hides_host(tmp_path: Path, mock: respx.MockRouter) -> None:
    mock.post(URL).mock(side_effect=httpx.ConnectError("cannot reach upstream.invalid"))
    async with LLMClient(_settings(tmp_path)) as client:
        with pytest.raises(LLMHTTPError, match="ConnectError") as exc:
            await client.complete(MESSAGES, data_class=DataClass.PUBLIC)
    assert "upstream.invalid" not in str(exc.value)
    assert exc.value.__cause__ is None
    assert exc.value.__suppress_context__


async def test_response_without_usage_is_rejected(tmp_path: Path, mock: respx.MockRouter) -> None:
    mock.post(URL).mock(
        return_value=httpx.Response(200, json={"model": "m", "choices": [{"message": {}}]})
    )
    async with LLMClient(_settings(tmp_path)) as client:
        with pytest.raises(LLMHTTPError, match="malformed"):
            await client.complete(MESSAGES, data_class=DataClass.PUBLIC)


# --- JSON schema helper and retry -------------------------------------------------------------


async def test_complete_json_sends_schema_and_validates(
    tmp_path: Path, mock: respx.MockRouter
) -> None:
    route = mock.post(URL).mock(return_value=_reply('{"verdict": "yes", "confidence": 0.9}'))
    async with LLMClient(_settings(tmp_path)) as client:
        answer = await client.complete_json(MESSAGES, Answer, data_class=DataClass.PUBLIC)
    assert answer == Answer(verdict="yes", confidence=0.9)
    rf = _body(route.calls.last)["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "Answer"
    assert rf["json_schema"]["schema"] == Answer.model_json_schema()
    assert route.call_count == 1


async def test_one_retry_appends_the_validation_error(
    tmp_path: Path, mock: respx.MockRouter
) -> None:
    route = mock.post(URL).mock(
        side_effect=[_reply('{"verdict": "yes"}'), _reply('{"verdict": "no", "confidence": 0.4}')]
    )
    async with LLMClient(_settings(tmp_path)) as client:
        answer = await client.complete_json(MESSAGES, Answer, data_class=DataClass.PUBLIC)
    assert answer.verdict == "no"
    assert route.call_count == 2
    retry_messages = _body(route.calls[1])["messages"]
    assert retry_messages[: len(MESSAGES)] == MESSAGES
    assert retry_messages[-2] == {"role": "assistant", "content": '{"verdict": "yes"}'}
    assert retry_messages[-1]["role"] == "user"
    assert "confidence: Field required" in retry_messages[-1]["content"]


async def test_second_invalid_output_raises_after_exactly_two_calls(
    tmp_path: Path, mock: respx.MockRouter
) -> None:
    route = mock.post(URL).mock(return_value=_reply("not json"))
    async with LLMClient(_settings(tmp_path)) as client:
        with pytest.raises(OutputValidationError, match="after 2 attempts"):
            await client.complete_json(MESSAGES, Answer, data_class=DataClass.PUBLIC)
    assert route.call_count == 2


# --- cassette modes ---------------------------------------------------------------------------


async def test_record_then_replay_with_network_blocked(
    tmp_path: Path, mock: respx.MockRouter
) -> None:
    route = mock.post(URL).mock(
        side_effect=[_reply('{"verdict": "x"}'), _reply('{"verdict": "y", "confidence": 1}')]
    )
    async with LLMClient(_settings(tmp_path, mode="record")) as client:
        recorded = await client.complete_json(
            MESSAGES, Answer, data_class=DataClass.PUBLIC, prompt_version="v1"
        )
    assert route.call_count == 2
    files = sorted((tmp_path / "unit").glob("*.json"))
    assert len(files) == 2  # one per attempt
    for f in files:
        assert KEY not in f.read_text(encoding="utf-8")
        assert "upstream.invalid" not in f.read_text(encoding="utf-8")

    mock.stop()  # from here on only the socket guard stands between us and the network
    async with LLMClient(_settings(tmp_path, mode="replay", base_url=None)) as client:
        replayed = await client.complete_json(
            MESSAGES, Answer, data_class=DataClass.PUBLIC, prompt_version="v1"
        )
    assert replayed == recorded


async def test_replay_miss_raises_and_never_calls_upstream(
    tmp_path: Path, mock: respx.MockRouter
) -> None:
    route = mock.post(URL).mock(return_value=_reply("ok"))
    async with LLMClient(_settings(tmp_path, mode="replay")) as client:
        with pytest.raises(CassetteMissError, match="re-record with `make eval-record`"):
            await client.complete(MESSAGES, data_class=DataClass.PUBLIC)
    assert route.call_count == 0


async def test_record_refuses_pii_before_calling(tmp_path: Path, mock: respx.MockRouter) -> None:
    route = mock.post(URL).mock(return_value=_reply("ok"))
    async with LLMClient(_settings(tmp_path, mode="record")) as client:
        with pytest.raises(CassetteWriteRefusedError, match="pii"):
            await client.complete(MESSAGES, data_class=DataClass.PII)
        with pytest.raises(CassetteWriteRefusedError, match="PII"):
            await client.complete(
                [{"role": "user", "content": "telp 081234567890"}], data_class=DataClass.INTERNAL
            )
    assert route.call_count == 0


async def test_live_writes_no_cassette(tmp_path: Path, mock: respx.MockRouter) -> None:
    mock.post(URL).mock(return_value=_reply("ok"))
    async with LLMClient(_settings(tmp_path, mode="live")) as client:
        await client.complete(MESSAGES, data_class=DataClass.PUBLIC)
    assert not (tmp_path / "unit").exists()


# --- limiter ----------------------------------------------------------------------------------


async def test_limiter_aborts_upstream_calls(tmp_path: Path, mock: respx.MockRouter) -> None:
    route = mock.post(URL).mock(return_value=_reply("ok", tokens=50))
    limiter = UsageLimiter(max_calls=10, max_total_tokens=100)
    async with LLMClient(_settings(tmp_path), limiter=limiter) as client:
        await client.complete(MESSAGES, data_class=DataClass.PUBLIC)
        await client.complete(MESSAGES, data_class=DataClass.PUBLIC)
        with pytest.raises(UsageLimitExceededError, match="token cap"):
            await client.complete(MESSAGES, data_class=DataClass.PUBLIC)
    assert route.call_count == 2
    assert (limiter.calls, limiter.total_tokens) == (2, 100)


async def test_replay_hits_do_not_count_against_limiter(
    tmp_path: Path, mock: respx.MockRouter
) -> None:
    mock.post(URL).mock(return_value=_reply("ok"))
    async with LLMClient(_settings(tmp_path, mode="record")) as client:
        await client.complete(MESSAGES, data_class=DataClass.PUBLIC)
    limiter = UsageLimiter(max_calls=1, max_total_tokens=1)
    async with LLMClient(_settings(tmp_path, mode="replay"), limiter=limiter) as client:
        for _ in range(3):
            await client.complete(MESSAGES, data_class=DataClass.PUBLIC)
    assert limiter.calls == 0


# --- tracing ----------------------------------------------------------------------------------


async def test_one_span_per_call_without_content(
    tmp_path: Path,
    mock: respx.MockRouter,
    spans: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    provider, exporter = spans
    mock.post(URL).mock(
        side_effect=[_reply('{"verdict": "x"}'), _reply('{"verdict": "y", "confidence": 1}')]
    )
    settings = _settings(tmp_path, mode="record")
    async with LLMClient(settings, tracer=provider.get_tracer("t")) as client:
        await client.complete_json(
            MESSAGES, Answer, data_class=DataClass.INTERNAL, task_tag="pdp.generate"
        )
    first, second = exporter.get_finished_spans()
    assert first.name == second.name == "llm.call"
    attrs = dict(second.attributes or {})
    assert attrs["gen_ai.request.model"] == "m1"
    assert attrs["gen_ai.response.model"] == "m1-2026"
    assert attrs["llm.data_class"] == "internal"
    assert attrs["llm.task_tag"] == "pdp.generate"
    assert attrs["llm.attempt"] == 2
    assert attrs["gen_ai.usage.input_tokens"] == 10
    assert attrs["gen_ai.usage.output_tokens"] == 5
    assert isinstance(attrs["llm.latency_ms"], float)
    assert attrs["llm.cassette"] == "miss"
    assert first.attributes is not None
    assert first.attributes["llm.attempt"] == 1
    dumped = json.dumps([dict(s.attributes or {}) for s in (first, second)])
    for needle in ("kewajiban", "verdict", "upstream.invalid", KEY):
        assert needle not in dumped
    for event in (*first.events, *second.events):
        assert "kewajiban" not in json.dumps(dict(event.attributes or {}))


async def test_replay_span_marks_hit_and_errors_carry_type_only(
    tmp_path: Path,
    mock: respx.MockRouter,
    spans: tuple[TracerProvider, InMemorySpanExporter],
) -> None:
    provider, exporter = spans
    mock.post(URL).mock(return_value=_reply("ok"))
    async with LLMClient(_settings(tmp_path, mode="record")) as client:
        await client.complete(MESSAGES, data_class=DataClass.PUBLIC)
    tracer = provider.get_tracer("t")
    async with LLMClient(_settings(tmp_path, mode="replay"), tracer=tracer) as client:
        await client.complete(MESSAGES, data_class=DataClass.PUBLIC)
        with pytest.raises(CassetteMissError):
            await client.complete(MESSAGES, data_class=DataClass.PUBLIC, seed=99)
    hit, miss = exporter.get_finished_spans()
    assert hit.attributes is not None
    assert miss.attributes is not None
    assert hit.attributes["llm.cassette"] == "hit"
    assert miss.attributes["llm.cassette"] == "miss"
    assert miss.attributes["error.type"] == "CassetteMissError"
    assert miss.events == ()
