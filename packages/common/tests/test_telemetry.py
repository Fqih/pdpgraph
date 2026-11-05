# SPDX-License-Identifier: Apache-2.0
"""OpenTelemetry setup (07 §4.1, NFR-09)."""

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from common.telemetry import setup_tracing


def test_spans_carry_service_name() -> None:
    exporter = InMemorySpanExporter()
    provider = setup_tracing("pdp-api", exporter=exporter, set_global=False)
    with provider.get_tracer("t").start_as_current_span("pdp.query"):
        pass
    (span,) = exporter.get_finished_spans()
    assert span.name == "pdp.query"
    assert span.resource.attributes["service.name"] == "pdp-api"


def test_sample_ratio_zero_records_nothing() -> None:
    exporter = InMemorySpanExporter()
    provider = setup_tracing("svc", exporter=exporter, sample_ratio=0.0, set_global=False)
    with provider.get_tracer("t").start_as_current_span("x"):
        pass
    assert exporter.get_finished_spans() == ()


@pytest.mark.parametrize("ratio", [-0.1, 1.5])
def test_sample_ratio_must_be_a_probability(ratio: float) -> None:
    with pytest.raises(ValueError, match="sample_ratio"):
        setup_tracing("svc", sample_ratio=ratio, set_global=False)


@pytest.mark.usefixtures("no_network")
def test_no_endpoint_means_no_export_and_no_network() -> None:
    provider = setup_tracing("svc", set_global=False)
    with provider.get_tracer("t").start_as_current_span("x"):
        pass
    assert provider.force_flush()
    provider.shutdown()


def test_sets_global_provider() -> None:
    provider = setup_tracing("svc", exporter=InMemorySpanExporter())
    assert trace.get_tracer_provider() is provider
