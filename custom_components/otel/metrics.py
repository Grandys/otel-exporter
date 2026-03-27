"""OpenTelemetry metrics conversion and export engine."""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_FRIENDLY_NAME,
    ATTR_TEMPERATURE,
    ATTR_UNIT_OF_MEASUREMENT,
    EVENT_STATE_CHANGED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import (
    area_registry as ar,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers.state import state_as_number

from .const import PROTOCOL_GRPC

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers.event import EventStateChangedData
    from opentelemetry.metrics import Counter, Gauge, Meter, MeterProvider

_LOGGER = logging.getLogger(__name__)

# Attribute keys as string literals to avoid cross-component import issues
ATTR_STATE_CLASS = "state_class"
ATTR_CURRENT_TEMPERATURE = "current_temperature"
ATTR_CURRENT_HUMIDITY = "current_humidity"
ATTR_CURRENT_POSITION = "current_position"
ATTR_BRIGHTNESS = "brightness"
ATTR_PERCENTAGE = "percentage"
ATTR_HUMIDITY = "humidity"
ATTR_WEATHER_TEMPERATURE = "temperature"
ATTR_WEATHER_HUMIDITY = "humidity"
ATTR_WEATHER_PRESSURE = "pressure"


class OtelMetricsManager:
    """Manages OpenTelemetry metric conversion and export."""

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        endpoint: str,
        protocol: str,
        auth_header: str | None,
        domains: set[str],
        export_interval_seconds: int,
    ) -> None:
        """Initialize the metrics manager."""
        self._hass = hass
        self._endpoint = endpoint
        self._protocol = protocol
        self._auth_header = auth_header
        self._domains = domains
        self._export_interval = export_interval_seconds

        # OTel SDK objects (initialized in setup())
        self._meter_provider: MeterProvider | None = None
        self._meter: Meter | None = None

        # Instrument caches
        self._gauges: dict[str, Gauge] = {}
        self._counters: dict[str, Counter] = {}

        # Previous values for counter delta computation
        self._previous_counter_values: dict[str, float] = {}

        # HA registries
        self._entity_registry: er.EntityRegistry | None = None
        self._device_registry: dr.DeviceRegistry | None = None
        self._area_registry: ar.AreaRegistry | None = None

        # Domain handler dispatch table
        self._domain_handlers: dict[str, Callable[[State, dict[str, str]], None]] = {
            "binary_sensor": self._handle_binary_sensor,
            "climate": self._handle_climate,
            "cover": self._handle_cover,
            "fan": self._handle_fan,
            "humidifier": self._handle_humidifier,
            "input_boolean": self._handle_binary_state,
            "input_number": self._handle_numeric_state,
            "light": self._handle_light,
            "lock": self._handle_binary_state,
            "number": self._handle_numeric_state,
            "sensor": self._handle_sensor,
            "switch": self._handle_binary_state,
            "water_heater": self._handle_water_heater,
            "weather": self._handle_weather,
        }

    def setup(self) -> None:
        """Set up the OTel MeterProvider and exporter in the executor."""
        from opentelemetry.sdk.metrics import MeterProvider  # noqa: PLC0415
        from opentelemetry.sdk.metrics.export import (  # noqa: PLC0415
            PeriodicExportingMetricReader,
        )
        from opentelemetry.sdk.resources import Resource  # noqa: PLC0415

        resource = Resource.create(
            {
                "service.name": "homeassistant",
                "ha.instance_name": self._hass.config.location_name,
            }
        )

        exporter = self._create_exporter()

        reader = PeriodicExportingMetricReader(
            exporter,
            export_interval_millis=self._export_interval * 1000,
        )

        self._meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[reader],
        )
        self._meter = self._meter_provider.get_meter("homeassistant.otel")

    def _create_exporter(self) -> Any:
        """Create the OTLP metric exporter based on configured protocol."""
        if self._protocol == PROTOCOL_GRPC:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (  # noqa: PLC0415
                OTLPMetricExporter,
            )

            headers = (
                (("authorization", self._auth_header),) if self._auth_header else None
            )
            return OTLPMetricExporter(
                endpoint=self._endpoint,
                headers=headers,
                insecure=self._endpoint.startswith("http://"),
            )

        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (  # noqa: PLC0415
            OTLPMetricExporter,
        )

        headers = {"authorization": self._auth_header} if self._auth_header else None
        return OTLPMetricExporter(
            endpoint=self._endpoint,
            headers=headers,
        )

    def start_listening(self, entry: ConfigEntry) -> None:
        """Register event listeners and bootstrap with current states."""
        self._entity_registry = er.async_get(self._hass)
        self._device_registry = dr.async_get(self._hass)
        self._area_registry = ar.async_get(self._hass)

        entry.async_on_unload(
            self._hass.bus.async_listen(
                EVENT_STATE_CHANGED, self._handle_state_changed_event
            )
        )

        # Bootstrap with current states
        for state in self._hass.states.async_all():
            if state.domain in self._domains:
                self._process_state(state)

    def shutdown(self) -> None:
        """Shut down the MeterProvider and flush pending metrics."""
        if self._meter_provider is not None:
            self._meter_provider.shutdown()
            self._meter_provider = None

    @callback
    def _handle_state_changed_event(self, event: Event[EventStateChangedData]) -> None:
        """Handle a state changed event."""
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        if new_state.domain not in self._domains:
            return

        if new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        self._process_state(new_state)

    def _process_state(self, state: State) -> None:
        """Convert an entity state to OTel metrics."""
        if self._meter is None:
            return

        labels = self._build_labels(state)
        handler = self._domain_handlers.get(state.domain)
        if handler is not None:
            handler(state, labels)

    def _build_labels(self, state: State) -> dict[str, str]:
        """Build OTel attribute labels for an entity state."""
        labels: dict[str, str] = {
            "entity_id": state.entity_id,
            "domain": state.domain,
            "friendly_name": state.attributes.get(ATTR_FRIENDLY_NAME, ""),
        }

        if device_class := state.attributes.get(ATTR_DEVICE_CLASS):
            labels["device_class"] = str(device_class)

        if unit := state.attributes.get(ATTR_UNIT_OF_MEASUREMENT):
            labels["unit"] = unit

        if self._entity_registry is not None:
            entity_entry = self._entity_registry.async_get(state.entity_id)
            if entity_entry is not None:
                self._add_area_and_device_labels(entity_entry, labels)

        return labels

    def _add_area_and_device_labels(
        self,
        entity_entry: er.RegistryEntry,
        labels: dict[str, str],
    ) -> None:
        """Add area and device labels from registry entries."""
        if self._device_registry is None or self._area_registry is None:
            return

        area_id = entity_entry.area_id
        device_name: str | None = None

        if entity_entry.device_id:
            device = self._device_registry.async_get(entity_entry.device_id)
            if device is not None:
                device_name = device.name_by_user or device.name
                if area_id is None:
                    area_id = device.area_id

        if device_name:
            labels["device_name"] = device_name

        if area_id:
            area = self._area_registry.async_get_area(area_id)
            if area is not None:
                labels["area"] = area.name

    # --- Instrument helpers ---

    def _require_meter(self) -> Meter:
        """Return the initialized meter or raise if setup has not completed."""
        if self._meter is None:
            msg = "OpenTelemetry meter has not been initialized"
            raise RuntimeError(msg)
        return self._meter

    def _get_gauge(self, name: str, unit: str = "", description: str = "") -> Gauge:
        """Get or create a cached Gauge instrument."""
        meter = self._require_meter()
        key = f"{name}:{unit}"
        if key not in self._gauges:
            self._gauges[key] = meter.create_gauge(
                name=name,
                unit=unit,
                description=description,
            )
        return self._gauges[key]

    def _get_counter(self, name: str, unit: str = "", description: str = "") -> Counter:
        """Get or create a cached Counter instrument."""
        meter = self._require_meter()
        key = f"{name}:{unit}"
        if key not in self._counters:
            self._counters[key] = meter.create_counter(
                name=name,
                unit=unit,
                description=description,
            )
        return self._counters[key]

    def _record_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str],
        unit: str = "",
        description: str = "",
    ) -> None:
        """Record a gauge metric value."""
        gauge = self._get_gauge(name, unit, description)
        gauge.set(value, labels)

    def _record_counter_delta(  # noqa: PLR0913
        self,
        name: str,
        entity_id: str,
        value: float,
        labels: dict[str, str],
        unit: str = "",
        description: str = "",
    ) -> None:
        """Record a counter metric delta for a monotonically increasing value."""
        counter = self._get_counter(name, unit, description)
        key = f"{name}:{entity_id}"
        previous = self._previous_counter_values.get(key)

        if previous is not None:
            delta = value - previous
            if delta > 0:
                counter.add(delta, labels)
            elif delta < 0:
                # Reset detected: treat new value as delta since reset
                counter.add(value, labels)
        # else: first observation, store value but don't record

        self._previous_counter_values[key] = value

    # --- Domain handlers ---

    def _handle_sensor(self, state: State, labels: dict[str, str]) -> None:
        """Handle sensor entity metrics."""
        try:
            value = float(state.state)
        except ValueError, TypeError:
            return

        state_class = state.attributes.get(ATTR_STATE_CLASS)
        device_class = state.attributes.get(ATTR_DEVICE_CLASS, "generic")
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT, "")

        if state_class == SensorStateClass.TOTAL_INCREASING:
            self._record_counter_delta(
                name=f"ha.sensor.{device_class}.total",
                entity_id=state.entity_id,
                value=value,
                labels=labels,
                unit=unit,
                description=f"Total increasing {device_class} sensor",
            )
        else:
            # MEASUREMENT, TOTAL, MEASUREMENT_ANGLE, or no state class
            self._record_gauge(
                name=f"ha.sensor.{device_class}",
                value=value,
                labels=labels,
                unit=unit,
                description=f"{device_class} sensor measurement",
            )

    def _handle_binary_sensor(self, state: State, labels: dict[str, str]) -> None:
        """Handle binary_sensor entity metrics."""
        try:
            value = float(state_as_number(state))
        except ValueError:
            return
        self._record_gauge(
            name="ha.binary_sensor.state",
            value=value,
            labels=labels,
            description="Binary sensor state (1=on, 0=off)",
        )

    def _handle_binary_state(self, state: State, labels: dict[str, str]) -> None:
        """Handle entities with simple on/off or locked/unlocked states."""
        try:
            value = float(state_as_number(state))
        except ValueError:
            return
        self._record_gauge(
            name=f"ha.{state.domain}.state",
            value=value,
            labels=labels,
            description=f"{state.domain} state",
        )

    def _handle_numeric_state(self, state: State, labels: dict[str, str]) -> None:
        """Handle entities with numeric states (number, input_number)."""
        try:
            value = float(state.state)
        except ValueError, TypeError:
            return
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT, "")
        self._record_gauge(
            name=f"ha.{state.domain}.state",
            value=value,
            labels=labels,
            unit=unit,
            description=f"{state.domain} value",
        )

    def _handle_light(self, state: State, labels: dict[str, str]) -> None:
        """Handle light entity metrics."""
        try:
            state_value = float(state_as_number(state))
        except ValueError:
            return

        brightness = state.attributes.get(ATTR_BRIGHTNESS)
        if brightness is not None:
            try:
                brightness_pct = float(brightness) / 255.0 * 100.0
            except ValueError, TypeError:
                brightness_pct = 0.0 if state_value == 0 else 100.0
        else:
            brightness_pct = 0.0 if state_value == 0 else 100.0

        self._record_gauge(
            name="ha.light.brightness_percent",
            value=brightness_pct,
            labels=labels,
            unit="%",
            description="Light brightness percentage",
        )

    def _handle_climate(self, state: State, labels: dict[str, str]) -> None:
        """Handle climate entity metrics."""
        current_temp = state.attributes.get(ATTR_CURRENT_TEMPERATURE)
        if current_temp is not None:
            with suppress(ValueError, TypeError):
                self._record_gauge(
                    name="ha.climate.current_temperature",
                    value=float(current_temp),
                    labels=labels,
                    description="Climate current temperature",
                )

        target_temp = state.attributes.get(ATTR_TEMPERATURE)
        if target_temp is not None:
            with suppress(ValueError, TypeError):
                self._record_gauge(
                    name="ha.climate.target_temperature",
                    value=float(target_temp),
                    labels=labels,
                    description="Climate target temperature",
                )

        current_humidity = state.attributes.get(ATTR_CURRENT_HUMIDITY)
        if current_humidity is not None:
            with suppress(ValueError, TypeError):
                self._record_gauge(
                    name="ha.climate.current_humidity",
                    value=float(current_humidity),
                    labels=labels,
                    unit="%",
                    description="Climate current humidity",
                )

    def _handle_cover(self, state: State, labels: dict[str, str]) -> None:
        """Handle cover entity metrics."""
        position = state.attributes.get(ATTR_CURRENT_POSITION)
        if position is not None:
            with suppress(ValueError, TypeError):
                self._record_gauge(
                    name="ha.cover.position",
                    value=float(position),
                    labels=labels,
                    unit="%",
                    description="Cover position percentage",
                )
        else:
            # Fall back to state as number (open=1, closed=0)
            try:
                value = float(state_as_number(state))
                self._record_gauge(
                    name="ha.cover.state",
                    value=value,
                    labels=labels,
                    description="Cover state (1=open, 0=closed)",
                )
            except ValueError:
                pass

    def _handle_fan(self, state: State, labels: dict[str, str]) -> None:
        """Handle fan entity metrics."""
        percentage = state.attributes.get(ATTR_PERCENTAGE)
        if percentage is not None:
            with suppress(ValueError, TypeError):
                self._record_gauge(
                    name="ha.fan.percentage",
                    value=float(percentage),
                    labels=labels,
                    unit="%",
                    description="Fan speed percentage",
                )
        else:
            try:
                value = float(state_as_number(state))
                self._record_gauge(
                    name="ha.fan.state",
                    value=value,
                    labels=labels,
                    description="Fan state (1=on, 0=off)",
                )
            except ValueError:
                pass

    def _handle_humidifier(self, state: State, labels: dict[str, str]) -> None:
        """Handle humidifier entity metrics."""
        try:
            state_value = float(state_as_number(state))
            self._record_gauge(
                name="ha.humidifier.state",
                value=state_value,
                labels=labels,
                description="Humidifier state (1=on, 0=off)",
            )
        except ValueError:
            pass

        humidity = state.attributes.get(ATTR_HUMIDITY)
        if humidity is not None:
            with suppress(ValueError, TypeError):
                self._record_gauge(
                    name="ha.humidifier.target_humidity",
                    value=float(humidity),
                    labels=labels,
                    unit="%",
                    description="Humidifier target humidity",
                )

    def _handle_water_heater(self, state: State, labels: dict[str, str]) -> None:
        """Handle water_heater entity metrics."""
        current_temp = state.attributes.get(ATTR_CURRENT_TEMPERATURE)
        if current_temp is not None:
            with suppress(ValueError, TypeError):
                self._record_gauge(
                    name="ha.water_heater.current_temperature",
                    value=float(current_temp),
                    labels=labels,
                    description="Water heater current temperature",
                )

        target_temp = state.attributes.get(ATTR_TEMPERATURE)
        if target_temp is not None:
            with suppress(ValueError, TypeError):
                self._record_gauge(
                    name="ha.water_heater.target_temperature",
                    value=float(target_temp),
                    labels=labels,
                    description="Water heater target temperature",
                )

    def _handle_weather(self, state: State, labels: dict[str, str]) -> None:
        """Handle weather entity metrics."""
        for attr, metric_name, unit, desc in (
            (
                ATTR_WEATHER_TEMPERATURE,
                "ha.weather.temperature",
                "",
                "Weather temperature",
            ),
            (ATTR_WEATHER_HUMIDITY, "ha.weather.humidity", "%", "Weather humidity"),
            (ATTR_WEATHER_PRESSURE, "ha.weather.pressure", "", "Weather pressure"),
        ):
            value = state.attributes.get(attr)
            if value is not None:
                with suppress(ValueError, TypeError):
                    self._record_gauge(
                        name=metric_name,
                        value=float(value),
                        labels=labels,
                        unit=unit,
                        description=desc,
                    )
