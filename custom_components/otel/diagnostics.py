"""Diagnostics support for the OpenTelemetry integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

from .const import CONF_AUTH_HEADER, CONF_ENDPOINT
from .otlp import redact_endpoint

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from . import OtelConfigEntry

TO_REDACT = {CONF_AUTH_HEADER}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: OtelConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    del hass

    runtime_data = entry.runtime_data if hasattr(entry, "runtime_data") else None

    diagnostics = {
        "entry": {
            **entry.data,
            CONF_ENDPOINT: redact_endpoint(entry.data[CONF_ENDPOINT]),
        },
        "options": dict(entry.options),
        "runtime": (
            runtime_data.metrics_manager.get_diagnostics()
            if runtime_data is not None
            else {"loaded": False}
        ),
    }

    return async_redact_data(diagnostics, TO_REDACT)
