"""Tests for diagnostics support."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from custom_components.otel.const import CONF_AUTH_HEADER, CONF_ENDPOINT, CONF_PROTOCOL
from custom_components.otel.diagnostics import async_get_config_entry_diagnostics


class DiagnosticsTests(unittest.TestCase):
    """Test diagnostics output."""

    def test_async_get_config_entry_diagnostics_redacts_sensitive_values(self) -> None:
        """Diagnostics should redact secrets and sanitize the endpoint."""
        entry = SimpleNamespace(
            data={
                CONF_ENDPOINT: "https://user:pass@example.com:4318/v1/metrics?token=abc",
                CONF_PROTOCOL: "http",
                CONF_AUTH_HEADER: "Bearer secret",
            },
            options={"domains": ["sensor"]},
            runtime_data=SimpleNamespace(
                metrics_manager=SimpleNamespace(
                    get_diagnostics=lambda: {"meter_initialized": True}
                )
            ),
        )

        diagnostics = asyncio.run(
            async_get_config_entry_diagnostics(SimpleNamespace(), entry)
        )

        assert (
            diagnostics["entry"][CONF_ENDPOINT] == "https://example.com:4318/v1/metrics"
        )
        assert diagnostics["entry"][CONF_AUTH_HEADER] == "**REDACTED**"
        assert diagnostics["runtime"] == {"meter_initialized": True}
