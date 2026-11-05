# SPDX-License-Identifier: Apache-2.0
"""Structured JSON logging with redaction (SEC-12, 07 §4.4).

Every event passes through `redact` before rendering: values under sensitive keys are masked,
secret-shaped strings (bearer tokens, API keys) and PII (`common.pii`) are replaced, and exact
runtime secret values passed to `configure_logging` (e.g. a private upstream host or key) are
removed. Fields: ts, level, service, event, request_id/trace_id when known, plus context.
"""

import logging
import re
import sys
from collections.abc import Iterable, Mapping, MutableMapping
from typing import Any, TextIO

import structlog
from opentelemetry import trace

from common.pii import redact_pii

REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "api_key",
        "api-key",
        "apikey",
        "x-api-key",
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "cookie",
        "set-cookie",
    }
)

_SECRET_PATTERNS = [
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password|passwd)(\s*[:=]\s*)\S+"),
]


def _redact_text(text: str, secrets: tuple[str, ...]) -> str:
    for value in secrets:
        text = text.replace(value, REDACTED)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(
            lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}" if m.lastindex else REDACTED, text
        )
    return redact_pii(text)


def redact(value: Any, secrets: Iterable[str] = ()) -> Any:
    """Recursively redact a log value (str, mapping, list/tuple); other types pass through."""
    secret_values = tuple(sorted({s for s in secrets if s}, key=len, reverse=True))
    return _redact(value, secret_values)


def _redact(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        return _redact_text(value, secrets)
    if isinstance(value, Mapping):
        return {
            k: REDACTED
            if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS
            else _redact(v, secrets)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [_redact(v, secrets) for v in value]
    return value


def _add_trace_context(
    _logger: Any, _method: str, event: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        event.setdefault("trace_id", format(ctx.trace_id, "032x"))
        event.setdefault("span_id", format(ctx.span_id, "016x"))
    return event


def configure_logging(
    service: str,
    *,
    level: str = "INFO",
    secrets: Iterable[str] = (),
    stream: TextIO | None = None,
) -> None:
    """Configure structlog for JSON output to `stream` (default stdout)."""
    secret_values = tuple(sorted({s for s in secrets if s}, key=len, reverse=True))

    def _add_service(
        _logger: Any, _method: str, event: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        event.setdefault("service", service)
        return event

    def _redact_event(
        _logger: Any, _method: str, event: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        redacted: MutableMapping[str, Any] = _redact(event, secret_values)
        return redacted

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _add_service,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            _add_trace_context,
            structlog.processors.format_exc_info,
            _redact_event,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=stream or sys.stdout),
        context_class=dict,
        cache_logger_on_first_use=False,
    )
