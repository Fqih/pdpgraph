# SPDX-License-Identifier: Apache-2.0
"""OpenAI-compatible LLM client (08 M0.5; FR-PDP-11, FR-PDP-18, ADR-015).

Every call carries a required `data_class` (no default) as `x-data-class`, plus an optional
`x-tierline-task` tag. Non-streaming only; streaming arrives with Tierline (M2). One OTel span
per upstream attempt, with metadata only: never message content, the host, or the key.
"""

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Literal, Self

import httpx
from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode, Tracer
from pydantic import BaseModel, Field, ValidationError

from common.llm.cassette import CassetteStore, canonical_request, cassette_key, check_recordable
from common.llm.errors import (
    CassetteMissError,
    LLMHTTPError,
    LocalOnlyDataClassError,
    OutputValidationError,
)
from common.llm.limiter import UsageLimiter
from common.llm.settings import LOCAL_ONLY, DataClass, LLMSettings

RETRY_PROMPT = (
    "Your previous reply did not match the required JSON schema:\n{errors}\n"
    "Reply again with only a JSON object that matches the schema."
)


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class _Message(BaseModel):
    content: str


class _Choice(BaseModel):
    message: _Message


class _ChatResponse(BaseModel):
    model: str
    choices: list[_Choice] = Field(min_length=1)
    usage: Usage


@dataclass(frozen=True, slots=True)
class Completion:
    content: str
    model: str  # as echoed by the upstream
    usage: Usage
    latency_ms: float
    cassette: Literal["hit", "miss", "off"]


def _validation_summary(exc: ValidationError) -> str:
    """Field paths and messages only; the offending input is left out."""
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    return "\n".join(f"- {'.'.join(map(str, e['loc'])) or '<root>'}: {e['msg']}" for e in errors)


class LLMClient:
    def __init__(
        self,
        settings: LLMSettings,
        *,
        limiter: UsageLimiter | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self._settings = settings
        self._limiter = limiter
        self._tracer = tracer or trace.get_tracer("common.llm")
        self._store = CassetteStore(
            settings.cassette_dir, settings.cassette_namespace, secrets=settings.secret_values()
        )
        self.timeout = httpx.Timeout(settings.read_timeout_s, connect=settings.connect_timeout_s)
        headers = dict(settings.extra_headers)
        if settings.api_key is not None:
            headers["Authorization"] = f"Bearer {settings.api_key.get_secret_value()}"
        self._http = httpx.AsyncClient(timeout=self.timeout, headers=headers)
        self._url = f"{(settings.base_url or '').rstrip('/')}/chat/completions"

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def complete(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        data_class: DataClass,
        task_tag: str | None = None,
        model: str | None = None,
        temperature: float | None = 0.0,
        top_p: float | None = None,
        max_tokens: int | None = None,
        seed: int | None = None,
        stop: Sequence[str] | None = None,
        response_format: Mapping[str, Any] | None = None,
        prompt_version: str | None = None,
        attempt: int = 1,
    ) -> Completion:
        data_class = DataClass(data_class)
        # Fail closed before anything is built. Replay sends nothing, so it is exempt.
        if (
            self._settings.mode != "replay"
            and data_class in LOCAL_ONLY
            and not self._settings.is_local_endpoint()
        ):
            raise LocalOnlyDataClassError(
                f"data_class={data_class} may only be sent to a local endpoint (ADR-013/015)"
            )
        request = canonical_request(
            model=model or self._settings.model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            seed=seed,
            stop=stop,
            response_format=response_format,
            prompt_version=prompt_version,
            attempt=attempt,
        )
        with self._tracer.start_as_current_span(
            "llm.call", record_exception=False, set_status_on_exception=False
        ) as span:
            span.set_attributes(
                {
                    "gen_ai.request.model": request["model"],
                    "llm.data_class": str(data_class),
                    "llm.attempt": attempt,
                    "llm.mode": self._settings.mode,
                }
            )
            if task_tag is not None:
                span.set_attribute("llm.task_tag", task_tag)
            try:
                result = await self._dispatch(request, response_format, data_class, task_tag, span)
            except Exception as exc:
                span.set_attribute("error.type", type(exc).__name__)
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                raise
            span.set_attributes(
                {
                    "gen_ai.response.model": result.model,
                    "gen_ai.usage.input_tokens": result.usage.prompt_tokens,
                    "gen_ai.usage.output_tokens": result.usage.completion_tokens,
                    "llm.latency_ms": result.latency_ms,
                }
            )
            return result

    async def complete_json[T: BaseModel](
        self,
        messages: Sequence[Mapping[str, str]],
        schema: type[T],
        *,
        data_class: DataClass,
        task_tag: str | None = None,
        model: str | None = None,
        temperature: float | None = 0.0,
        max_tokens: int | None = None,
        seed: int | None = None,
        prompt_version: str | None = None,
    ) -> T:
        """Request JSON matching `schema`; on a validation failure retry once with the error
        appended to the prompt (FR-PDP-11)."""
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "strict": True,
                "schema": schema.model_json_schema(),
            },
        }
        prompt = list(messages)
        errors = ""
        for attempt in (1, 2):
            result = await self.complete(
                prompt,
                data_class=data_class,
                task_tag=task_tag,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                seed=seed,
                response_format=response_format,
                prompt_version=prompt_version,
                attempt=attempt,
            )
            try:
                return schema.model_validate_json(result.content)
            except ValidationError as exc:
                errors = _validation_summary(exc)
                prompt = [
                    *messages,
                    {"role": "assistant", "content": result.content},
                    {"role": "user", "content": RETRY_PROMPT.format(errors=errors)},
                ]
        raise OutputValidationError(
            f"output failed {schema.__name__} validation after 2 attempts:\n{errors}"
        )

    async def _dispatch(
        self,
        request: dict[str, Any],
        response_format: Mapping[str, Any] | None,
        data_class: DataClass,
        task_tag: str | None,
        span: Span,
    ) -> Completion:
        mode = self._settings.mode
        if mode == "replay":
            return self._replay(request, span)
        span.set_attribute("llm.cassette", "miss" if mode == "record" else "off")
        if mode == "record":
            check_recordable(data_class, request)  # before anything leaves the process
        body = {k: v for k, v in request.items() if v is not None and k in _UPSTREAM_FIELDS}
        if response_format is not None:
            body["response_format"] = response_format  # full schema, not the hashed form
        headers = {"x-data-class": str(data_class)}
        if task_tag is not None:
            headers["x-tierline-task"] = task_tag
        raw, parsed, latency_ms = await self._post({**body, "stream": False}, headers)
        if mode == "record":
            self._store.put(
                request=request,
                data_class=data_class,
                task_tag=task_tag,
                response=raw,
                latency_ms=latency_ms,
            )
        return _completion(parsed, latency_ms, "miss" if mode == "record" else "off")

    def _replay(self, request: dict[str, Any], span: Span) -> Completion:
        key = cassette_key(request)
        entry = self._store.get(key)
        span.set_attribute("llm.cassette", "miss" if entry is None else "hit")
        if entry is None:
            raise CassetteMissError(
                f"no cassette for key {key[:12]} in namespace "
                f"{self._settings.cassette_namespace!r}; re-record with `make eval-record`"
            )
        parsed = _ChatResponse.model_validate(entry["response"])
        return _completion(parsed, float(entry["latency_ms"]), "hit")

    async def _post(
        self, body: dict[str, Any], headers: dict[str, str]
    ) -> tuple[dict[str, Any], _ChatResponse, float]:
        if self._limiter is not None:
            self._limiter.acquire()
        start = time.perf_counter()
        try:
            response = await self._http.post(self._url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            # `from None`: httpx messages carry the URL, which must not reach logs or traces.
            raise LLMHTTPError(f"upstream request failed: {type(exc).__name__}") from None
        latency_ms = (time.perf_counter() - start) * 1000
        if response.is_error:
            raise LLMHTTPError(f"upstream returned HTTP {response.status_code}")
        try:
            parsed = _ChatResponse.model_validate_json(response.content)
        except ValidationError:
            raise LLMHTTPError("malformed upstream response (choices/usage)") from None
        if self._limiter is not None:
            self._limiter.add_tokens(parsed.usage.total_tokens)
        raw: dict[str, Any] = response.json()
        return raw, parsed, latency_ms


_UPSTREAM_FIELDS = frozenset(
    {"model", "messages", "temperature", "top_p", "max_tokens", "seed", "stop"}
)


def _completion(
    parsed: _ChatResponse, latency_ms: float, cassette: Literal["hit", "miss", "off"]
) -> Completion:
    return Completion(
        content=parsed.choices[0].message.content,
        model=parsed.model,
        usage=parsed.usage,
        latency_ms=latency_ms,
        cassette=cassette,
    )
