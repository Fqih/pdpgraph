# SPDX-License-Identifier: Apache-2.0
"""Structured logging with redaction (SEC-12, 07 §4.4). All values are synthetic."""

import io
import json
from typing import Any

import pytest
import structlog
from opentelemetry.sdk.trace import TracerProvider

from common.logging import configure_logging, redact


@pytest.fixture
def capture() -> io.StringIO:
    return io.StringIO()


def _lines(buf: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in buf.getvalue().splitlines()]


def test_sec_12_json_fields(capture: io.StringIO) -> None:
    configure_logging("pdp-api", stream=capture)
    structlog.contextvars.bind_contextvars(request_id="r-1")
    try:
        structlog.get_logger().info("retrieval_completed", hits=3)
    finally:
        structlog.contextvars.clear_contextvars()
    (line,) = _lines(capture)
    assert line["event"] == "retrieval_completed"
    assert line["service"] == "pdp-api"
    assert line["level"] == "info"
    assert line["request_id"] == "r-1"
    assert line["hits"] == 3
    assert "ts" in line


def test_level_filtering(capture: io.StringIO) -> None:
    configure_logging("svc", level="WARNING", stream=capture)
    structlog.get_logger().info("hidden")
    structlog.get_logger().warning("shown")
    assert [line["event"] for line in _lines(capture)] == ["shown"]


SECRET_SAMPLES = [
    "Authorization: Bearer abc.def-ghi_jkl123",
    "key sk-test1234567890abcdefXYZ",
    "token ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "api_key=supersecretvalue123",
    "password: hunter2hunter2",
]


@pytest.mark.parametrize("text", SECRET_SAMPLES)
def test_sec_12_redacts_secret_patterns(text: str) -> None:
    out = redact(text)
    assert "[REDACTED" in out
    for token in ("abc.def-ghi_jkl123", "sk-test1234567890", "ghp_abc", "supersecret", "hunter2"):
        assert token not in out


@pytest.mark.parametrize(
    ("text", "leak"),
    [
        ("nik 3171012345678901", "3171012345678901"),
        ("hp +6281234567890", "6281234567890"),
        ("mail budi@contoh.co.id", "budi@contoh.co.id"),
    ],
)
def test_sec_12_redacts_pii(text: str, leak: str) -> None:
    assert leak not in redact(text)


def test_sec_12_sensitive_keys_are_masked_whatever_the_value() -> None:
    event = {"headers": {"Authorization": "x", "X-Api-Key": "y", "accept": "json"}, "token": "t"}
    assert redact(event) == {
        "headers": {"Authorization": "[REDACTED]", "X-Api-Key": "[REDACTED]", "accept": "json"},
        "token": "[REDACTED]",
    }


def test_sec_12_runtime_secret_values_are_redacted(capture: io.StringIO) -> None:
    configure_logging("svc", stream=capture, secrets=["upstream.internal.example:9999", "k-123"])
    structlog.get_logger().info(
        "upstream_called", url="http://upstream.internal.example:9999/v1", note=["used k-123"]
    )
    raw = capture.getvalue()
    assert "upstream.internal.example" not in raw
    assert "k-123" not in raw


def test_sec_12_redacts_nested_values_and_exceptions(capture: io.StringIO) -> None:
    configure_logging("svc", stream=capture)
    try:
        raise ValueError("bad phone 081234567890")
    except ValueError:
        structlog.get_logger().exception("failed", ctx={"items": ("mail a@b.co.id", 1)})
    raw = capture.getvalue()
    assert "081234567890" not in raw
    assert "a@b.co.id" not in raw
    assert _lines(capture)[0]["ctx"]["items"][1] == 1


def test_trace_ids_from_active_span(capture: io.StringIO) -> None:
    configure_logging("svc", stream=capture)
    tracer = TracerProvider().get_tracer("t")
    with tracer.start_as_current_span("s") as span:
        structlog.get_logger().info("inside")
        trace_id = format(span.get_span_context().trace_id, "032x")
    structlog.get_logger().info("outside")
    inside, outside = _lines(capture)
    assert inside["trace_id"] == trace_id
    assert "trace_id" not in outside
