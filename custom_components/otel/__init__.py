"""The OpenTelemetry integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_AUTH_HEADER,
    CONF_DOMAINS,
    CONF_ENDPOINT,
    CONF_EXPORT_INTERVAL,
    CONF_PROTOCOL,
    DEFAULT_EXPORT_INTERVAL,
    METRIC_DOMAINS,
)
from .metrics import OtelMetricsManager

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

type OtelConfigEntry = ConfigEntry[OtelRuntimeData]


@dataclass
class OtelRuntimeData:
    """Runtime data for the OpenTelemetry integration."""

    metrics_manager: OtelMetricsManager


async def async_setup_entry(hass: HomeAssistant, entry: OtelConfigEntry) -> bool:
    """Set up OpenTelemetry from a config entry."""
    endpoint = entry.data[CONF_ENDPOINT]
    protocol = entry.data[CONF_PROTOCOL]
    auth_header = entry.data.get(CONF_AUTH_HEADER)
    domains = set(entry.options.get(CONF_DOMAINS, METRIC_DOMAINS))
    export_interval = entry.options.get(CONF_EXPORT_INTERVAL, DEFAULT_EXPORT_INTERVAL)

    metrics_manager = OtelMetricsManager(
        hass=hass,
        endpoint=endpoint,
        protocol=protocol,
        auth_header=auth_header,
        domains=domains,
        export_interval_seconds=int(export_interval),
    )

    await hass.async_add_executor_job(metrics_manager.setup)

    metrics_manager.start_listening(entry)

    entry.runtime_data = OtelRuntimeData(metrics_manager=metrics_manager)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: OtelConfigEntry) -> bool:
    """Unload an OpenTelemetry config entry."""
    await hass.async_add_executor_job(entry.runtime_data.metrics_manager.shutdown)
    return True
