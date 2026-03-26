# Home Assistant OpenTelemetry Exporter

Custom Home Assistant integration that exports Home Assistant entity state changes as OpenTelemetry metrics to an OTLP endpoint.

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

1. In Home Assistant, go to `Settings -> Devices & services -> Add integration`.
2. Search for `OpenTelemetry Exporter`.
3. Enter:
   - OTLP endpoint
   - protocol (`gRPC` or `HTTP`)
   - optional authorization header
4. After setup, open the integration options to choose exported domains and export interval.

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
