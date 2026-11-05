# SPDX-License-Identifier: Apache-2.0
"""OpenTelemetry tracing setup (07 §4.1, ADR-008, NFR-09).

Spans are exported over OTLP/HTTP only when an endpoint (or an explicit exporter) is given;
otherwise nothing leaves the process. Use `tracer.start_as_current_span(name)` as a context
manager or decorator (it supports sync and async functions).
"""

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased


def setup_tracing(
    service_name: str,
    *,
    endpoint: str | None = None,
    sample_ratio: float = 1.0,
    exporter: SpanExporter | None = None,
    set_global: bool = True,
) -> TracerProvider:
    """Create a tracer provider for `service_name`.

    `endpoint` is the OTLP/HTTP traces URL (e.g. the collector). `exporter` overrides it and
    exports synchronously (tests). `sample_ratio` defaults to 1.0 (100% in dev, NFR-09).
    """
    if not 0.0 <= sample_ratio <= 1.0:
        raise ValueError(f"sample_ratio must be within [0, 1], got {sample_ratio}")
    provider = TracerProvider(
        resource=Resource.create({SERVICE_NAME: service_name}),
        sampler=ParentBased(TraceIdRatioBased(sample_ratio)),
    )
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    elif endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    if set_global:
        trace.set_tracer_provider(provider)
    return provider
