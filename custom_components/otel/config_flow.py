"""Config flow for the OpenTelemetry integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
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

_LOGGER = logging.getLogger(__name__)

PROTOCOL_OPTIONS = [
    {"value": PROTOCOL_GRPC, "label": "gRPC"},
    {"value": PROTOCOL_HTTP, "label": "HTTP"},
]

USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ENDPOINT, default=DEFAULT_ENDPOINT): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        vol.Required(CONF_PROTOCOL, default=DEFAULT_PROTOCOL): SelectSelector(
            SelectSelectorConfig(
                options=PROTOCOL_OPTIONS,
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_AUTH_HEADER): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


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
        errors: dict[str, str] = {}

        if user_input is not None:
            endpoint = user_input[CONF_ENDPOINT]
            protocol = user_input[CONF_PROTOCOL]
            auth_header = user_input.get(CONF_AUTH_HEADER)

            try:
                await self.hass.async_add_executor_job(
                    _validate_endpoint, endpoint, protocol, auth_header
                )
            except ConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during validation")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title="OpenTelemetry",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=USER_DATA_SCHEMA,
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


def _validate_endpoint(endpoint: str, protocol: str, auth_header: str | None) -> None:
    """Validate the OTLP endpoint by attempting to create an exporter."""
    try:
        if protocol == PROTOCOL_GRPC:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (  # noqa: PLC0415
                OTLPMetricExporter as OTLPMetricExporterGrpc,
            )

            headers = (("authorization", auth_header),) if auth_header else None
            exporter = OTLPMetricExporterGrpc(
                endpoint=endpoint,
                headers=headers,
                insecure=endpoint.startswith("http://"),
                timeout=5,
            )
        else:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (  # noqa: PLC0415
                OTLPMetricExporter as OTLPMetricExporterHttp,
            )

            headers = {"authorization": auth_header} if auth_header else None
            exporter = OTLPMetricExporterHttp(
                endpoint=endpoint,
                headers=headers,
                timeout=5,
            )
        exporter.shutdown()
    except Exception as err:
        msg = f"Cannot create OTLP exporter for {endpoint}"
        raise ConnectionError(msg) from err
