"""Tests for runtime metric export health tracking."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from custom_components.otel.const import DOMAIN, ISSUE_ID_EXPORT_FAILED
from custom_components.otel.metrics import OtelMetricsManager


class _FakeHass:
    """Minimal Home Assistant stub for metrics manager tests."""

    def __init__(self) -> None:
        """Initialize the fake Home Assistant object."""
        self.config = SimpleNamespace(location_name="Test Home")

    def add_job(self, target, *args) -> None:
        """Run scheduled jobs immediately."""
        target(*args)


class MetricsManagerTests(unittest.TestCase):
    """Test export health tracking."""

    @patch("custom_components.otel.metrics.issue_registry.async_delete_issue")
    @patch("custom_components.otel.metrics.issue_registry.async_create_issue")
    def test_export_failures_create_and_clear_issue(
        self,
        async_create_issue: MagicMock,
        async_delete_issue: MagicMock,
    ) -> None:
        """A repair issue should appear after repeated failures."""
        manager = OtelMetricsManager(
            hass=_FakeHass(),
            endpoint="https://user:pass@example.com:4318/v1/metrics?token=123",
            protocol="http",
            auth_header=None,
            domains={"sensor"},
            export_interval_seconds=60,
        )

        manager._handle_export_failure()
        manager._handle_export_failure()
        async_create_issue.assert_not_called()

        manager._handle_export_failure()

        async_create_issue.assert_called_once()
        create_args = async_create_issue.call_args
        assert create_args.args[:3] == (
            manager._hass,
            DOMAIN,
            ISSUE_ID_EXPORT_FAILED,
        )
        assert create_args.kwargs["translation_placeholders"] == {
            "endpoint": "https://example.com:4318/v1/metrics",
            "failure_count": "3",
        }

        diagnostics = manager.get_diagnostics()
        assert diagnostics["consecutive_export_failures"] == 3
        assert diagnostics["total_export_failures"] == 3
        assert diagnostics["export_failure_issue_active"] is True
        assert diagnostics["last_export_result"] == "failure"

        manager._handle_export_success()

        async_delete_issue.assert_called_once_with(
            manager._hass,
            DOMAIN,
            ISSUE_ID_EXPORT_FAILED,
        )
        diagnostics = manager.get_diagnostics()
        assert diagnostics["consecutive_export_failures"] == 0
        assert diagnostics["total_export_failures"] == 3
        assert diagnostics["export_failure_issue_active"] is False
        assert diagnostics["last_export_result"] == "success"
