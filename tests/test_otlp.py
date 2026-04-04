"""Tests for OTLP helper functions."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests
from grpc import RpcError, StatusCode
from opentelemetry.sdk.metrics.export import MetricExportResult

from custom_components.otel.const import PROTOCOL_GRPC, PROTOCOL_HTTP
from custom_components.otel.otlp import (
    OtelAuthenticationError,
    OtelConnectionError,
    TrackingMetricExporter,
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

    @patch("custom_components.otel.otlp.create_metric_exporter")
    def test_validate_http_authentication_error(
        self,
        create_metric_exporter: MagicMock,
    ) -> None:
        """HTTP validation should classify 401 responses as auth failures."""
        exporter = SimpleNamespace(
            _export=MagicMock(return_value=SimpleNamespace(ok=False, status_code=401)),
            shutdown=MagicMock(),
        )
        create_metric_exporter.return_value = exporter

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

        exporter.shutdown.assert_called_once_with()

    @patch("custom_components.otel.otlp.create_metric_exporter")
    def test_validate_http_connection_error(
        self,
        create_metric_exporter: MagicMock,
    ) -> None:
        """HTTP validation should classify request failures as connectivity issues."""
        exporter = SimpleNamespace(
            _export=MagicMock(side_effect=requests.exceptions.ConnectionError),
            shutdown=MagicMock(),
        )
        create_metric_exporter.return_value = exporter

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

        exporter.shutdown.assert_called_once_with()

    @patch("custom_components.otel.otlp.create_metric_exporter")
    def test_validate_grpc_authentication_error(
        self,
        create_metric_exporter: MagicMock,
    ) -> None:
        """GRPC validation should classify unauthenticated failures as auth errors."""
        exporter = SimpleNamespace(
            _client=SimpleNamespace(
                Export=MagicMock(side_effect=_FakeRpcError(StatusCode.UNAUTHENTICATED))
            ),
            _translate_data=MagicMock(return_value=object()),
            _headers=(("authorization", "Bearer secret"),),
            shutdown=MagicMock(),
        )
        create_metric_exporter.return_value = exporter

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

        exporter.shutdown.assert_called_once_with()
