"""Tests for integration setup behavior."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from homeassistant.exceptions import ConfigEntryAuthFailed

import custom_components.otel as integration
from custom_components.otel.const import (
    CONF_AUTH_HEADER,
    CONF_ENDPOINT,
    CONF_PROTOCOL,
    DEFAULT_EXPORT_INTERVAL,
    PROTOCOL_HTTP,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class _FakeHass:
    """Minimal Home Assistant stub for setup tests."""

    async def async_add_executor_job(
        self,
        target: Callable[..., object],
        *args: object,
    ) -> object:
        """Run executor jobs inline during tests."""
        return target(*args)


class SetupEntryTests(unittest.TestCase):
    """Test config entry setup handling."""

    @patch("custom_components.otel.issue_registry.async_delete_issue")
    @patch("custom_components.otel.validate_metric_exporter_connection")
    @patch("custom_components.otel.OtelMetricsManager")
    def test_async_setup_entry_success(
        self,
        metrics_manager_cls: MagicMock,
        validate_metric_exporter_connection: MagicMock,
        async_delete_issue: MagicMock,
    ) -> None:
        """Successful setup should validate, initialize, and start listening."""
        metrics_manager = MagicMock()
        metrics_manager_cls.return_value = metrics_manager
        entry = SimpleNamespace(
            data={
                CONF_ENDPOINT: "https://collector.example.com/v1/metrics",
                CONF_PROTOCOL: PROTOCOL_HTTP,
                CONF_AUTH_HEADER: "Bearer secret",
            },
            options={},
        )

        result = asyncio.run(integration.async_setup_entry(_FakeHass(), entry))

        assert result is True
        validate_metric_exporter_connection.assert_called_once_with(
            "https://collector.example.com/v1/metrics",
            PROTOCOL_HTTP,
            "Bearer secret",
        )
        metrics_manager_cls.assert_called_once()
        metrics_manager.setup.assert_called_once_with()
        metrics_manager.start_listening.assert_called_once_with(entry)
        assert entry.runtime_data.metrics_manager is metrics_manager
        assert async_delete_issue.call_count == 2

    @patch("custom_components.otel.issue_registry.async_create_issue")
    @patch(
        "custom_components.otel.validate_metric_exporter_connection",
        side_effect=integration.OtelAuthenticationError("bad auth"),
    )
    def test_async_setup_entry_auth_failure_creates_issue(
        self,
        validate_metric_exporter_connection: MagicMock,
        async_create_issue: MagicMock,
    ) -> None:
        """Authentication failures should surface as ConfigEntryAuthFailed."""
        entry = SimpleNamespace(
            data={
                CONF_ENDPOINT: "https://collector.example.com/v1/metrics",
                CONF_PROTOCOL: PROTOCOL_HTTP,
                CONF_AUTH_HEADER: "Bearer secret",
            },
            options={
                "export_interval": DEFAULT_EXPORT_INTERVAL,
            },
        )

        try:
            asyncio.run(integration.async_setup_entry(_FakeHass(), entry))
        except ConfigEntryAuthFailed as err:
            assert "OTLP authentication failed" in str(err)
        else:
            self.fail("Expected ConfigEntryAuthFailed")

        validate_metric_exporter_connection.assert_called_once()
        async_create_issue.assert_called_once()
