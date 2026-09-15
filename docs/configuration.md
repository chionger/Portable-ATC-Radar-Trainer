# FP-002 configuration

The application loads typed, immutable settings before startup. Configuration loading reads only
the packaged defaults and an explicitly selected YAML file. It does not create data directories,
inspect model storage, run inference, or select models.

## Precedence

From lowest to highest: packaged `defaults.yaml`, optional local YAML, `ATC_` environment variables,
then explicit `--host` / `--port` launcher arguments. Nested groups merge by field. YAML must be a
mapping with unique string keys; unsafe YAML tags, unknown fields, invalid types and unsupported
schema versions are rejected. Malformed source syntax is rejected even if a later source would
override it. No local file is discovered automatically.

Select YAML with `--config` or `ATC_CONFIG_FILE`. An explicit `--config` wins over `ATC_CONFIG_FILE`.
An explicitly selected missing or unreadable file prevents startup.

## Settings reference

| YAML field | Environment variable | Default / accepted values |
| --- | --- | --- |
| `schema_version` | `ATC_SCHEMA_VERSION` | String `1.0` |
| `api.host` | `ATC_API_HOST` | `127.0.0.1`; also `localhost`, `::1` |
| `api.port` | `ATC_API_PORT` | `8000`; integer 1–65535 |
| `api.cors_origins` | `ATC_API_CORS_ORIGINS` | Loopback HTTP origins on port 5173; JSON array in environment |
| `paths.data_root` | `ATC_PATHS_DATA_ROOT` | `~/.portable-atc-radar-trainer/data` |
| `paths.model_root` | `ATC_PATHS_MODEL_ROOT` | `null` (unconfigured); explicit absolute local directory |
| `logging.level` | `ATC_LOGGING_LEVEL` | `INFO`; DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `features.report_configuration` | `ATC_FEATURES_REPORT_CONFIGURATION` | `false`; JSON `true` / `false` |

Only the listed `ATC_` variables and `ATC_CONFIG_FILE` are accepted. Unrelated environment variables
are ignored. String settings use literal environment text; ports, booleans and arrays use JSON.
Use the exact string `null` to clear the model path in the environment.

Paths accept absolute local paths or `~/` home shorthand. Relative paths, drive-relative Windows
paths, filesystem roots, traversal components, UNC/device paths and reserved Windows names are
rejected. Validation is lexical: it does not check existence, permissions or symlink targets.
Later file operations must enforce their own storage boundaries. An unset model root is valid
because FP-002 does not load models. Never configure model assets inside the Git checkout.

## Run and inspect

From the repository root:

```powershell
python -m scripts.run_api --show-config
python -m scripts.run_api --config config.local.yaml --port 8100
```

Copy `docs/configuration.example.yaml` to the ignored `config.local.yaml` and edit only the fields
you need. Keep private configuration out of Git.

```powershell
.\scripts\start-dev.ps1 -Config .\config.local.yaml -ApiPort 8100
```

The development launcher passes explicit overrides to the API and sets `VITE_API_URL` to its
effective address for the child frontend process, restoring the previous value on exit. The Vite
development port remains 5173; configure allowed origins if running the frontend elsewhere.

The legacy `python -m uvicorn apps.api.main:app` entry point still validates YAML/environment settings
and supports default startup. Uvicorn owns its host, port and log options in that mode: use
`scripts.run_api` to apply those settings consistently to the server.

## Reporting, hashing and health

`--show-config` prints JSON with both local paths redacted and a SHA-256 configuration hash; it
does not start the API. The optional `report_configuration` flag logs the same safe report.
There are no credential settings in FP-002: unknown credential fields are rejected. Validation
errors name the field and error type without echoing supplied values or YAML source lines.

The hash covers the validated effective settings, including normalized paths, as UTF-8 canonical
JSON (sorted keys and compact separators). Key order and source precedence history do not affect
it. Changes to effective values do. Local paths mean hashes can differ between machines. This
hash is a configuration identifier, not a signature or an asset-integrity check; no model bytes
are read or hashed. A future secret-bearing field will need an explicit hash/redaction policy.

`GET /health` returns only:

```json
{"status":"ok","configuration_version":"1.0"}
```

The version identifies the configuration schema; the full effective hash and settings remain
local. Domain/session persistence and model-specific tuning remain in later feature packets.
