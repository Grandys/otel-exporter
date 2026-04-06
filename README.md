# Home Assistant OpenTelemetry Exporter

Custom Home Assistant integration that exports Home Assistant entity state changes as OpenTelemetry metrics to an OTLP endpoint.

It is meant for setups where Home Assistant data should be available outside the built-in Home Assistant UI. Instead of keeping telemetry only in Home Assistant dashboards, history views, and recorder-backed charts, this integration sends entity measurements to a standard OpenTelemetry pipeline so they can be stored, queried, correlated, and visualized in tools such as Grafana, New Relic, and other OTLP-compatible backends.

In practice, it solves a simple problem: Home Assistant is good at automation and local status views, but it is not a general observability platform. This integration lets you treat Home Assistant signals like regular telemetry data.

## Features

- Config flow based setup
- OTLP over gRPC or HTTP
- Optional authorization header support
- Selectable entity domains
- Configurable export interval

## Installation

### HACS

1. Open HACS.
2. Go to `Integrations`.
3. Open the menu and choose `Custom repositories`.
4. Add `https://github.com/Grandys/otel-exporter` with category `Integration`.
5. Install `Home Assistant OpenTelemetry Exporter`.
6. Restart Home Assistant.

### Manual

1. Copy `custom_components/otel` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.

## Configuration

Open the config flow directly in your Home Assistant instance:

[![Open your Home Assistant instance and start setting up OpenTelemetry Exporter.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=otel)

1. In Home Assistant, go to `Settings -> Devices & services -> Add integration`.
2. Search for `OpenTelemetry Exporter`.
3. Enter:
   - OTLP endpoint
   - protocol (`gRPC` or `HTTP`)
   - optional authorization header
4. After setup, open the integration options to choose exported domains and export interval.

## Local Example Setup

This repository includes a local example stack:

- Home Assistant started from the Python virtual environment
- OpenTelemetry Collector started by Docker Compose
- Grafana LGTM started by Docker Compose
- Demo Home Assistant entities in [config/configuration.yaml](/Users/michalgrandys/Documents/Personal/otel-exporter/config/configuration.yaml) that emit changing values automatically

### 1. Create and activate the virtual environment

If you do not already have `.venv`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If `.venv` already exists:

```bash
source .venv/bin/activate
```

### 2. Start local Home Assistant

Run:

```bash
./scripts/develop
```

This will:

- start the local Docker stack from [compose.yaml](/Users/michalgrandys/Documents/Personal/otel-exporter/compose.yaml)
- start the OpenTelemetry Collector using [otel-collector/config.yaml](/Users/michalgrandys/Documents/Personal/otel-exporter/otel-collector/config.yaml)
- launch Home Assistant with the local config in [config/configuration.yaml](/Users/michalgrandys/Documents/Personal/otel-exporter/config/configuration.yaml)

### 3. Configure the integration in local Home Assistant

Open Home Assistant and add the integration from `Settings -> Devices & services -> Add integration`.

Use one of these local collector endpoints:

- gRPC endpoint: `http://localhost:4317`
- HTTP endpoint: `http://localhost:4318/v1/metrics`

Recommended local settings:

- protocol: `gRPC`
- authorization header: leave empty
- exported domains: include at least `input_boolean`, `input_number`, and `sensor`
- export interval: `10` or `15` seconds for quick local feedback

### 4. What Home Assistant will emit

The local config includes demo signals:

- `input_boolean.otel_demo_enabled` toggles every 15 seconds
- `input_number.otel_demo_temperature` changes every 15 seconds
- `sensor.otel_demo_power` is derived from the demo temperature

That means the exporter should continuously send changing metrics without any manual interaction.

### 5. What to expect in Grafana

Open LGTM at `http://localhost:3000`.

What you should expect:

- the Docker stack contains both `lgtm` and `otel-collector`
- the collector accepts metrics on ports `4317` and `4318`
- the collector forwards metrics into LGTM
- after the integration is configured, you should start seeing Home Assistant metrics appear within a few export intervals

In Grafana, look for metric names such as:

- `ha.input_boolean.state`
- `ha.input_number.state`
- `ha.sensor.generic`

You should also expect labels like:

- `entity_id`
- `domain`
- `friendly_name`
- `unit`

For the bundled demo setup specifically, the most useful entities to filter on are:

- `input_boolean.otel_demo_enabled`
- `input_number.otel_demo_temperature`
- `sensor.otel_demo_power`

If everything is working, the Grafana graphs should show:

- a toggling boolean signal for `otel_demo_enabled`
- a step-like changing numeric signal for `otel_demo_temperature`
- a matching derived numeric signal for `otel_demo_power`

### 6. Quick checks if nothing appears in Grafana

- Confirm `docker compose ps` shows both `otel-collector` and `lgtm` running
- Confirm Home Assistant accepted the integration configuration
- Check the Home Assistant log output in the terminal started by `./scripts/develop`
- Check collector logs with `docker logs <collector-container>`
- Verify the endpoint/protocol pair matches:
  - `http://localhost:4317` with `gRPC`
  - `http://localhost:4318/v1/metrics` with `HTTP`

## Development

- `scripts/setup` installs local development dependencies.
- `scripts/develop` runs Home Assistant with the bundled test configuration.
- `scripts/lint` runs formatting and lint checks.

## Repository layout

- `custom_components/otel` contains the HACS-installable integration.
- `config` contains the local Home Assistant development configuration.
- `.github/workflows/validate.yml` runs `hassfest` and HACS validation.

## Support

- Issues: <https://github.com/Grandys/otel-exporter/issues>
- HACS publishing docs: <https://hacs.xyz/docs/publish/start/>
