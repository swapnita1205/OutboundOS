from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.utils.settings import Settings


def configure_otel(settings: Settings) -> None:
    if not settings.otel_enabled:
        return

    provider = TracerProvider(resource=Resource.create({"service.name": settings.service_name}))
    if settings.otel_exporter_otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


def instrument_fastapi(app: FastAPI) -> None:
    FastAPIInstrumentor.instrument_app(app)
