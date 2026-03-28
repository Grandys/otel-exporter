"""Config flow for the OpenTelemetry integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_AUTH_HEADER,
    CONF_DOMAINS,
    CONF_ENDPOINT,
    CONF_EXPORT_INTERVAL,
    CONF_PROTOCOL,
    DEFAULT_ENDPOINT,
    DEFAULT_EXPORT_INTERVAL,
    DEFAULT_PROTOCOL,
    DOMAIN,
    METRIC_DOMAINS,
    PROTOCOL_GRPC,
    PROTOCOL_HTTP,
)
from .otlp import (
    OtelAuthenticationError,
    OtelConnectionError,
    validate_metric_exporter_connection,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

_LOGGER = logging.getLogger(__name__)

PROTOCOL_OPTIONS = [
    {"value": PROTOCOL_GRPC, "label": "gRPC"},
    {"value": PROTOCOL_HTTP, "label": "HTTP"},
]


def _build_connection_schema(defaults: Mapping[str, Any] | None = None) -> vol.Schema:
    """Build the connection settings schema with defaults."""
    data = defaults or {}

    return vol.Schema(
        {
            vol.Required(
                CONF_ENDPOINT,
                default=data.get(CONF_ENDPOINT, DEFAULT_ENDPOINT),
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
            vol.Required(
                CONF_PROTOCOL,
                default=data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=PROTOCOL_OPTIONS,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_AUTH_HEADER,
                default=data.get(CONF_AUTH_HEADER, ""),
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        }
    )


def _normalize_connection_data(user_input: Mapping[str, Any]) -> dict[str, str]:
    """Normalize the connection data stored in the config entry."""
    normalized = {
        CONF_ENDPOINT: str(user_input[CONF_ENDPOINT]).strip(),
        CONF_PROTOCOL: str(user_input[CONF_PROTOCOL]).strip(),
    }

    auth_header = str(user_input.get(CONF_AUTH_HEADER, "")).strip()
    if auth_header:
        normalized[CONF_AUTH_HEADER] = auth_header

    return normalized


class OtelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenTelemetry."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        _config_entry: ConfigEntry,
    ) -> OtelOptionsFlowHandler:
        """Get the options flow for this handler."""
        return OtelOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        return await self._async_handle_connection_step(
            step_id="user",
            user_input=user_input,
        )

    async def async_step_reconfigure(
        self,
        user_input: Mapping[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle reconfiguration."""
        return await self._async_handle_connection_step(
            step_id="reconfigure",
            user_input=user_input,
            existing_data=self._get_reconfigure_entry().data,
        )

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],
    ) -> ConfigFlowResult:
        """Start reauthentication."""
        return await self.async_step_reauth_confirm(entry_data)

    async def async_step_reauth_confirm(
        self,
        user_input: Mapping[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle reauthentication."""
        return await self._async_handle_connection_step(
            step_id="reauth_confirm",
            user_input=user_input,
            existing_data=self._get_reauth_entry().data,
        )

    async def _async_handle_connection_step(
        self,
        step_id: str,
        user_input: Mapping[str, Any] | None = None,
        existing_data: Mapping[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle a connection settings form."""
        errors: dict[str, str] = {}
        form_data = dict(existing_data or {})

        if user_input is not None:
            normalized_data = _normalize_connection_data(user_input)

            try:
                await self.hass.async_add_executor_job(
                    validate_metric_exporter_connection,
                    normalized_data[CONF_ENDPOINT],
                    normalized_data[CONF_PROTOCOL],
                    normalized_data.get(CONF_AUTH_HEADER),
                )
            except OtelAuthenticationError:
                errors["base"] = "invalid_auth"
            except OtelConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during validation")
                errors["base"] = "unknown"
            else:
                if self.source == SOURCE_RECONFIGURE:
                    return self.async_update_reload_and_abort(
                        self._get_reconfigure_entry(),
                        data=normalized_data,
                        reason="reconfigure_successful",
                    )

                if self.source == SOURCE_REAUTH:
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(),
                        data_updates=normalized_data,
                        reason="reauth_successful",
                    )

                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="OpenTelemetry",
                    data=normalized_data,
                )

            form_data = normalized_data

        return self.async_show_form(
            step_id=step_id,
            data_schema=_build_connection_schema(form_data),
            errors=errors,
        )


class OtelOptionsFlowHandler(OptionsFlowWithReload):
    """Handle OpenTelemetry options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_domains = self.config_entry.options.get(CONF_DOMAINS, METRIC_DOMAINS)
        current_interval = self.config_entry.options.get(
            CONF_EXPORT_INTERVAL, DEFAULT_EXPORT_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DOMAINS, default=current_domains): SelectSelector(
                        SelectSelectorConfig(
                            options=METRIC_DOMAINS,
                            multiple=True,
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key="domains",
                        )
                    ),
                    vol.Required(
                        CONF_EXPORT_INTERVAL, default=current_interval
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=10,
                            max=600,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                }
            ),
        )
