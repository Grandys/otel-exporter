"""OTLP exporter helpers shared across config flow and runtime setup."""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

import requests
from grpc import RpcError, StatusCode
from opentelemetry.exporter.otlp.proto.common.metrics_encoder import encode_metrics
from opentelemetry.sdk.metrics.export import (
    MetricExporter,
    MetricExportResult,
    MetricsData,
)

from .const import PROTOCOL_GRPC, VALIDATION_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from collections.abc import Callable

    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter as OTLPMetricExporterGrpc,
    )
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter as OTLPMetricExporterHttp,
    )

_LOGGER = logging.getLogger(__name__)


class OtelConnectionError(Exception):
    """Raised when the OTLP endpoint cannot be reached or rejects the request."""


class OtelAuthenticationError(OtelConnectionError):
    """Raised when the OTLP endpoint rejects authentication."""


class TrackingMetricExporter(MetricExporter):
    """Metric exporter wrapper that reports export success and failure."""

    def __init__(
        self,
        exporter: MetricExporter,
        on_success: Callable[[], None] | None = None,
        on_failure: Callable[[], None] | None = None,
    ) -> None:
        """Initialize the tracking exporter."""
        super().__init__(
            preferred_temporality=exporter._preferred_temporality,  # noqa: SLF001
            preferred_aggregation=exporter._preferred_aggregation,  # noqa: SLF001
        )
        self._exporter = exporter
        self._on_success = on_success
        self._on_failure = on_failure

    def export(
        self,
        metrics_data: MetricsData,
        timeout_millis: float = 10_000,
        **kwargs: object,
    ) -> MetricExportResult:
        """Export metrics and report the outcome."""
        try:
            result = self._exporter.export(
                metrics_data,
                timeout_millis=timeout_millis,
                **kwargs,
            )
        except Exception:
            self._notify(self._on_failure, "failure")
            raise

        if result is MetricExportResult.SUCCESS:
            self._notify(self._on_success, "success")
        else:
            self._notify(self._on_failure, "failure")

        return result

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        """Flush the wrapped exporter."""
        return self._exporter.force_flush(timeout_millis=timeout_millis)

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: object) -> None:
        """Shut down the wrapped exporter."""
        self._exporter.shutdown(timeout_millis=timeout_millis, **kwargs)

    def _notify(
        self,
        callback: Callable[[], None] | None,
        outcome: str,
    ) -> None:
        """Invoke an export callback without breaking the exporter thread."""
        if callback is None:
            return

        try:
            callback()
        except Exception:
            _LOGGER.exception("Unexpected exception while handling OTLP %s", outcome)


def create_metric_exporter(
    endpoint: str,
    protocol: str,
    auth_header: str | None,
    timeout_seconds: float | None = None,
) -> OTLPMetricExporterGrpc | OTLPMetricExporterHttp:
    """Create an OTLP metric exporter for the configured protocol."""
    timeout = timeout_seconds or VALIDATION_TIMEOUT_SECONDS

    if protocol == PROTOCOL_GRPC:
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (  # noqa: PLC0415
            OTLPMetricExporter,
        )

        headers = (("authorization", auth_header),) if auth_header else None
        return OTLPMetricExporter(
            endpoint=endpoint,
            headers=headers,
            insecure=endpoint.startswith("http://"),
            timeout=timeout,
        )

    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (  # noqa: PLC0415
        OTLPMetricExporter,
    )

    headers = {"authorization": auth_header} if auth_header else None
    return OTLPMetricExporter(
        endpoint=endpoint,
        headers=headers,
        timeout=timeout,
    )


def validate_metric_exporter_connection(
    endpoint: str,
    protocol: str,
    auth_header: str | None,
    timeout_seconds: float = VALIDATION_TIMEOUT_SECONDS,
) -> None:
    """Validate that the configured OTLP endpoint accepts a metrics export."""
    exporter = create_metric_exporter(
        endpoint=endpoint,
        protocol=protocol,
        auth_header=auth_header,
        timeout_seconds=timeout_seconds,
    )

    try:
        metrics_data = MetricsData(resource_metrics=[])
        if protocol == PROTOCOL_GRPC:
            _validate_grpc_exporter(exporter, metrics_data, timeout_seconds)
        else:
            _validate_http_exporter(exporter, metrics_data, timeout_seconds)
    finally:
        exporter.shutdown()


def redact_endpoint(endpoint: str) -> str:
    """Return a sanitized endpoint safe to include in diagnostics."""
    parsed = urlsplit(endpoint)

    if not parsed.netloc:
        return endpoint

    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    sanitized_netloc = f"{host}{port}"

    return urlunsplit(
        (
            parsed.scheme,
            sanitized_netloc,
            parsed.path,
            "",
            "",
        )
    )


def _validate_grpc_exporter(
    exporter: OTLPMetricExporterGrpc | OTLPMetricExporterHttp,
    metrics_data: MetricsData,
    timeout_seconds: float,
) -> None:
    """Validate a gRPC exporter by sending an empty export request."""
    grpc_exporter = exporter
    try:
        if grpc_exporter._client is None:  # noqa: SLF001
            msg = "The gRPC OTLP exporter client could not be initialized"
            raise OtelConnectionError(msg)

        grpc_exporter._client.Export(  # noqa: SLF001
            request=grpc_exporter._translate_data(metrics_data),  # noqa: SLF001
            metadata=grpc_exporter._headers,  # noqa: SLF001
            timeout=timeout_seconds,
        )
    except RpcError as err:
        if err.code() in (
            StatusCode.UNAUTHENTICATED,
            StatusCode.PERMISSION_DENIED,
        ):
            msg = "The OTLP endpoint rejected the authentication header"
            raise OtelAuthenticationError(msg) from err

        msg = f"Unable to export metrics to the OTLP gRPC endpoint: {err.code()}"
        raise OtelConnectionError(msg) from err


def _validate_http_exporter(
    exporter: OTLPMetricExporterGrpc | OTLPMetricExporterHttp,
    metrics_data: MetricsData,
    timeout_seconds: float,
) -> None:
    """Validate an HTTP exporter by posting an empty export payload."""
    serialized_data = encode_metrics(metrics_data).SerializeToString()

    try:
        response = exporter._export(serialized_data, timeout_seconds)  # noqa: SLF001
    except requests.exceptions.RequestException as err:
        msg = "Unable to reach the OTLP HTTP endpoint"
        raise OtelConnectionError(msg) from err

    if response.ok:
        return

    if response.status_code in {
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.FORBIDDEN,
    }:
        msg = "The OTLP endpoint rejected the authentication header"
        raise OtelAuthenticationError(msg)

    msg = f"Unable to export metrics to the OTLP HTTP endpoint: {response.status_code}"
    raise OtelConnectionError(msg)
