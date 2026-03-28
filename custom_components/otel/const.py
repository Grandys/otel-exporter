"""Constants for the OpenTelemetry integration."""

from typing import Final

DOMAIN: Final = "otel"
EXPORT_FAILURE_THRESHOLD: Final = 3
ISSUE_ID_EXPORT_FAILED: Final = "export_failed"
ISSUE_ID_INVALID_AUTH: Final = "invalid_auth"

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
VALIDATION_TIMEOUT_SECONDS: Final = 5.0

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
