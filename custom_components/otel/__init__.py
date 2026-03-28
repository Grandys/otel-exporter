"""The OpenTelemetry integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import issue_registry

from .const import (
    CONF_AUTH_HEADER,
    CONF_DOMAINS,
    CONF_ENDPOINT,
    CONF_EXPORT_INTERVAL,
    CONF_PROTOCOL,
    DEFAULT_EXPORT_INTERVAL,
    DOMAIN,
    ISSUE_ID_EXPORT_FAILED,
    ISSUE_ID_INVALID_AUTH,
    METRIC_DOMAINS,
)
from .metrics import OtelMetricsManager
from .otlp import (
    OtelAuthenticationError,
    OtelConnectionError,
    validate_metric_exporter_connection,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

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

    try:
        await hass.async_add_executor_job(
            validate_metric_exporter_connection,
            endpoint,
            protocol,
            auth_header,
        )
    except OtelAuthenticationError as err:
        issue_registry.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_ID_INVALID_AUTH,
            is_fixable=True,
            is_persistent=True,
            severity=issue_registry.IssueSeverity.ERROR,
            translation_key="invalid_auth",
        )
        msg = "OTLP authentication failed"
        raise ConfigEntryAuthFailed(msg) from err
    except OtelConnectionError as err:
        _LOGGER.warning("Unable to connect to OTLP endpoint %s: %s", endpoint, err)
        msg = f"Unable to connect to OTLP endpoint {endpoint}"
        raise ConfigEntryNotReady(msg) from err

    issue_registry.async_delete_issue(hass, DOMAIN, ISSUE_ID_INVALID_AUTH)
    issue_registry.async_delete_issue(hass, DOMAIN, ISSUE_ID_EXPORT_FAILED)

    metrics_manager = OtelMetricsManager(
        hass=hass,
        endpoint=endpoint,
        protocol=protocol,
        auth_header=auth_header,
        domains=domains,
        export_interval_seconds=int(export_interval),
    )

    try:
        await hass.async_add_executor_job(metrics_manager.setup)
    except Exception as err:
        msg = f"Unable to initialize the OTLP exporter for {endpoint}"
        raise ConfigEntryNotReady(msg) from err

    metrics_manager.start_listening(entry)

    entry.runtime_data = OtelRuntimeData(metrics_manager=metrics_manager)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: OtelConfigEntry) -> bool:
    """Unload an OpenTelemetry config entry."""
    await hass.async_add_executor_job(entry.runtime_data.metrics_manager.shutdown)
    return True
