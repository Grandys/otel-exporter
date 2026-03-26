"""Constants for the OpenTelemetry integration."""

from typing import Final

DOMAIN: Final = "otel"

CONF_ENDPOINT: Final = "endpoint"
CONF_PROTOCOL: Final = "protocol"
CONF_AUTH_HEADER: Final = "auth_header"
CONF_DOMAINS: Final = "domains"
CONF_EXPORT_INTERVAL: Final = "export_interval"

PROTOCOL_GRPC: Final = "grpc"
PROTOCOL_HTTP: Final = "http"

DEFAULT_ENDPOINT: Final = "http://localhost:4317"
DEFAULT_EXPORT_INTERVAL: Final = 60
DEFAULT_PROTOCOL: Final = PROTOCOL_GRPC

# Domains that produce numeric metrics
METRIC_DOMAINS: Final[list[str]] = [
    "binary_sensor",
    "climate",
    "cover",
    "fan",
    "humidifier",
    "input_boolean",
    "input_number",
    "light",
    "lock",
    "number",
    "sensor",
    "switch",
    "water_heater",
    "weather",
]
