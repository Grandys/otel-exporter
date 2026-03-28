# Home Assistant OpenTelemetry Exporter

Custom Home Assistant integration that exports Home Assistant entity state changes as OpenTelemetry metrics to an OTLP endpoint.

## Features

- Config flow based setup
- OTLP over gRPC or HTTP
- Optional authorization header support
- Selectable entity domains
- Configurable export interval
- OTLP endpoint validation during setup and startup
- Reconfigure and reauthentication support from the UI
- Diagnostics support for bug reports

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

1. In Home Assistant, go to `Settings -> Devices & services -> Add integration`.
2. Search for `OpenTelemetry Exporter`.
3. Enter:
   - OTLP endpoint
   - protocol (`gRPC` or `HTTP`)
   - optional authorization header
4. After setup, open the integration options to choose exported domains and export interval.
5. If the collector endpoint or token changes later, use the integration `Reconfigure` action instead of deleting and recreating the entry.

## Endpoint examples

- gRPC: `http://otel-collector.local:4317`
- HTTP: `http://otel-collector.local:4318/v1/metrics`

## Local LGTM example

This repository now includes a local example stack that runs:

- Grafana LGTM in Docker via [compose.yaml](/Users/michalgrandys/Documents/Personal/otel-exporter/compose.yaml)
- An OpenTelemetry Collector that forwards metrics into LGTM via [otel-collector/config.yaml](/Users/michalgrandys/Documents/Personal/otel-exporter/otel-collector/config.yaml)
- A Home Assistant dev config with demo entities in [configuration.yaml](/Users/michalgrandys/Documents/Personal/otel-exporter/config/configuration.yaml)

Start the full example stack with:

```bash
docker compose up -d
./scripts/develop
```

Or just run:

```bash
./scripts/develop
```

because it now starts Docker services automatically before launching Home Assistant.

Use these local endpoints inside the integration:

- gRPC: `http://localhost:4317`
- HTTP: `http://localhost:4318/v1/metrics`

Open LGTM at `http://localhost:3000` after the stack starts. Metrics from the demo Home Assistant entities will appear there through the collector pipeline.

The collector configuration used by the example stack is:

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:

exporters:
  debug:
  otlphttp/lgtm:
    endpoint: http://lgtm:4318

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug, otlphttp/lgtm]
```

## Exported data

- Metrics are emitted with names such as `ha.sensor.temperature`, `ha.light.brightness_percent`, and `ha.climate.current_temperature`.
- Labels include `entity_id`, `domain`, `friendly_name`, and, when available, `device_class`, `unit`, `device_name`, and `area`.
- `total_increasing` sensors are exported as counter deltas. Most other supported entity values are exported as gauges.

## Development

- `scripts/setup` installs local development dependencies.
- `scripts/develop` starts the local Docker example stack and then runs Home Assistant with the bundled test configuration.
- `scripts/lint` runs formatting and lint checks.
- `scripts/test` runs the unit test suite.

## Troubleshooting

- Setup now validates the OTLP endpoint before saving the entry. If setup fails, confirm the protocol and endpoint path match your collector.
- Authentication failures create a Home Assistant issue and can be fixed through the integration reauthentication or reconfigure flow.
- Repeated runtime export failures create a Home Assistant repair issue automatically after several failed export attempts and clear once exports recover.
- For bug reports, include the integration diagnostics dump from Home Assistant along with debug logs.
- If you are testing against a collector that requires authentication, verify the header format expected by that receiver, for example `Bearer <token>`.
- If the local example stack is not running, verify `docker compose ps` shows both `otel-collector` and `lgtm` healthy and reachable on ports `4317`, `4318`, and `3000`.

## Limitations

- This integration exports metrics only; it does not export Home Assistant traces or logs.
- Only the configured entity domains are exported.
- Metric availability depends on the entity state and attributes being numeric or convertible to numeric values.

## Repository layout

- `compose.yaml` runs the local LGTM example stack.
- `otel-collector/config.yaml` defines the collector pipeline used by the local example stack.
- `custom_components/otel` contains the HACS-installable integration.
- `config` contains the local Home Assistant development configuration.
- `.github/workflows/validate.yml` runs `hassfest` and HACS validation.
- `.github/workflows/lint.yml` runs Ruff and the unit test suite.

## Support

- Issues: <https://github.com/Grandys/otel-exporter/issues>
- HACS publishing docs: <https://hacs.xyz/docs/publish/start/>
