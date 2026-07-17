# DEALData Documentation

This directory contains operator, contributor, and community documentation for DEALData.

## Start Here

- Repository overview and local validation: `../README.md`
- Contributor rules: `../CONTRIBUTING.md`
- Support boundaries: `../SUPPORT.md`
- Security reporting: `../SECURITY.md`
- WildFi HTTP and Kafka contract: `api-contracts.md`
- Progressive refactor roadmap: `refactor-roadmap.md`
- Community guide: `community/README.md`

## Scope

DEALData provides the Django data services behind the DEAL suite:

- `core_layer` for projects, members, observed objects, and experiments.
- `gps_layer` for GPS data and WildFi `raw.gps` persistence.
- `sensor_layer` for sensor data and WildFi `raw.sensor` persistence.
- `dealdata_common` for shared ingestion, model, serializer, and Kafka helpers.

Documentation should stay practical: describe reproducible setup, validation commands, data contracts, operational impact, and support boundaries.
