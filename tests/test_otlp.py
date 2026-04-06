"""Tests for OTLP helper functions."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests
from grpc import RpcError, StatusCode
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter as OTLPMetricExporterGrpc,
)
from opentelemetry.sdk.metrics.export import MetricExportResult

from custom_components.otel.const import PROTOCOL_GRPC, PROTOCOL_HTTP
from custom_components.otel.otlp import (
    OtelAuthenticationError,
    OtelConnectionError,
    TrackingMetricExporter,
    _create_grpc_channel,
    _resolve_grpc_endpoint,
    create_metric_exporter,
    redact_endpoint,
    validate_metric_exporter_connection,
)


class _FakeRpcError(RpcError):
    """Minimal RpcError implementation for tests."""

    def __init__(self, status_code: StatusCode) -> None:
        """Initialize the fake RPC error."""
        super().__init__()
        self._status_code = status_code

    def code(self) -> StatusCode:
        """Return the status code for the fake gRPC failure."""
        return self._status_code


class OtlpHelperTests(unittest.TestCase):
    """Test OTLP helper behavior."""

    def test_tracking_metric_exporter_reports_success(self) -> None:
        """Successful exports should trigger the success callback."""
        on_success = MagicMock()
        on_failure = MagicMock()
        exporter = SimpleNamespace(
            _preferred_temporality=None,
            _preferred_aggregation=None,
            export=MagicMock(return_value=MetricExportResult.SUCCESS),
            force_flush=MagicMock(return_value=True),
            shutdown=MagicMock(),
        )

        tracking_exporter = TrackingMetricExporter(
            exporter=exporter,
            on_success=on_success,
            on_failure=on_failure,
        )

        result = tracking_exporter.export(SimpleNamespace())

        assert result is MetricExportResult.SUCCESS
        on_success.assert_called_once_with()
        on_failure.assert_not_called()

    def test_tracking_metric_exporter_reports_failure_result(self) -> None:
        """Failed exports should trigger the failure callback."""
        on_success = MagicMock()
        on_failure = MagicMock()
        exporter = SimpleNamespace(
            _preferred_temporality=None,
            _preferred_aggregation=None,
            export=MagicMock(return_value=MetricExportResult.FAILURE),
            force_flush=MagicMock(return_value=True),
            shutdown=MagicMock(),
        )

        tracking_exporter = TrackingMetricExporter(
            exporter=exporter,
            on_success=on_success,
            on_failure=on_failure,
        )

        result = tracking_exporter.export(SimpleNamespace())

        assert result is MetricExportResult.FAILURE
        on_failure.assert_called_once_with()
        on_success.assert_not_called()

    def test_redact_endpoint_removes_userinfo_and_query(self) -> None:
        """Endpoint redaction should keep only the safe URL parts."""
        assert (
            redact_endpoint("https://user:pass@example.com:4318/v1/metrics?api_key=123")
            == "https://example.com:4318/v1/metrics"
        )

    def test_resolve_grpc_endpoint_accepts_bare_target(self) -> None:
        """Bare gRPC targets should be treated as insecure host:port values."""
        assert _resolve_grpc_endpoint("localhost:4317") == ("localhost:4317", True)

    def test_resolve_grpc_endpoint_accepts_https_url(self) -> None:
        """HTTPS gRPC URLs should preserve the host:port and remain secure."""
        assert _resolve_grpc_endpoint("https://collector.example.com:4317") == (
            "collector.example.com:4317",
            False,
        )

    @patch("custom_components.otel.otlp.requests.post")
    def test_validate_http_authentication_error(self, post: MagicMock) -> None:
        """HTTP validation should classify 401 responses as auth failures."""
        post.return_value = SimpleNamespace(
            ok=False,
            status_code=401,
        )

        try:
            validate_metric_exporter_connection(
                "https://collector.example.com/v1/metrics",
                PROTOCOL_HTTP,
                "Bearer secret",
            )
        except OtelAuthenticationError as err:
            assert "authentication header" in str(err)
        else:
            self.fail("Expected OtelAuthenticationError")

        post.assert_called_once()

    @patch("custom_components.otel.otlp.requests.post")
    def test_validate_http_connection_error(self, post: MagicMock) -> None:
        """HTTP validation should classify request failures as connectivity issues."""
        post.side_effect = requests.exceptions.ConnectionError

        try:
            validate_metric_exporter_connection(
                "https://collector.example.com/v1/metrics",
                PROTOCOL_HTTP,
                None,
            )
        except OtelConnectionError as err:
            assert "Unable to reach" in str(err)
        else:
            self.fail("Expected OtelConnectionError")

        post.assert_called_once()

    @patch("custom_components.otel.otlp.requests.post")
    def test_validate_http_includes_auth_header(self, post: MagicMock) -> None:
        """HTTP validation should send the configured authorization header."""
        post.return_value = SimpleNamespace(ok=True, status_code=200)

        validate_metric_exporter_connection(
            "https://collector.example.com/v1/metrics",
            PROTOCOL_HTTP,
            "Bearer secret",
        )

        post.assert_called_once()
        assert post.call_args.kwargs["headers"]["authorization"] == "Bearer secret"
        assert (
            post.call_args.kwargs["headers"]["content-type"] == "application/x-protobuf"
        )

    @patch("custom_components.otel.otlp.MetricsServiceStub")
    @patch("custom_components.otel.otlp._create_grpc_channel")
    def test_validate_grpc_authentication_error(
        self,
        create_grpc_channel: MagicMock,
        metrics_service_stub: MagicMock,
    ) -> None:
        """GRPC validation should classify unauthenticated failures as auth errors."""
        channel = MagicMock()
        stub = MagicMock()
        stub.Export.side_effect = _FakeRpcError(StatusCode.UNAUTHENTICATED)
        create_grpc_channel.return_value = channel
        metrics_service_stub.return_value = stub

        try:
            validate_metric_exporter_connection(
                "http://collector.example.com:4317",
                PROTOCOL_GRPC,
                "Bearer secret",
            )
        except OtelAuthenticationError as err:
            assert "authentication header" in str(err)
        else:
            self.fail("Expected OtelAuthenticationError")

        metrics_service_stub.assert_called_once_with(channel)
        stub.Export.assert_called_once()
        channel.close.assert_called_once_with()

    @patch("custom_components.otel.otlp.secure_channel")
    @patch("custom_components.otel.otlp.insecure_channel")
    def test_create_grpc_channel_uses_insecure_transport_for_bare_target(
        self,
        insecure: MagicMock,
        secure: MagicMock,
    ) -> None:
        """Bare host:port gRPC targets should use an insecure channel."""
        _create_grpc_channel("collector.example.com:4317")
        insecure.assert_called_once_with("collector.example.com:4317")
        secure.assert_not_called()

    def test_create_metric_exporter_supports_bare_grpc_target(self) -> None:
        """Runtime exporter creation should support host:port gRPC targets."""
        exporter = create_metric_exporter("localhost:4317", PROTOCOL_GRPC, None)
        try:
            assert isinstance(exporter, OTLPMetricExporterGrpc)
            assert exporter._insecure is True
        finally:
            exporter.shutdown()
