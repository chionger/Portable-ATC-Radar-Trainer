from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path, PureWindowsPath
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class ConfigurationError(ValueError):
    """A field-specific configuration error that contains no supplied values."""


class StrictSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class ApiSettings(StrictSettings):
    host: Literal["127.0.0.1", "::1", "localhost"]
    port: Annotated[int, Field(ge=1, le=65535)]
    cors_origins: tuple[str, ...]

    @field_validator("cors_origins")
    @classmethod
    def local_origins(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("expected a loopback HTTP origin")
            _ = parsed.port  # Reject invalid or out-of-range URL ports.
        return origins


def absolute_local_path(value: str) -> str:
    """Validate lexically, without probing storage or following symlinks."""
    windows = PureWindowsPath(value)
    if (
        not value
        or any(ord(char) < 32 for char in value)
        or value.startswith(("\\\\", "//"))
        or ".." in value.replace("\\", "/").split("/")
        or any(char in value for char in '*?<>|"')
    ):
        raise ValueError("expected a safe absolute local path")
    if windows.drive:
        if not re.fullmatch(r"[A-Za-z]:", windows.drive) or not windows.is_absolute():
            raise ValueError("expected an absolute local drive path")
        if any(":" in part or part.endswith((".", " ")) for part in windows.parts[1:]):
            raise ValueError("invalid Windows path component")
        if any(PureWindowsPath(part).is_reserved() for part in windows.parts[1:]):
            raise ValueError("reserved Windows path component")
        if len(windows.parts) < 2:
            raise ValueError("a filesystem root is not a data directory")
        return str(windows)
    path = Path(value)
    if not path.is_absolute() or path == Path(path.anchor):
        raise ValueError("expected an absolute local directory path")
    return str(path)


class PathSettings(StrictSettings):
    data_root: str
    model_root: str | None

    @field_validator("data_root", "model_root")
    @classmethod
    def local_path(cls, value: str | None) -> str | None:
        return absolute_local_path(value) if value is not None else None


class LoggingSettings(StrictSettings):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    file_path: str | None = None
    max_bytes: Annotated[int, Field(ge=1024, le=100_000_000)] = 1_000_000
    backup_count: Annotated[int, Field(ge=1, le=10)] = 3

    @field_validator("file_path")
    @classmethod
    def local_log(cls, value: str | None) -> str | None:
        return absolute_local_path(value) if value is not None else None


class HealthSettings(StrictSettings):
    timeout_seconds: Annotated[float, Field(gt=0, le=3600, allow_inf_nan=False)] = 30.0


class FeatureSettings(StrictSettings):
    report_configuration: bool


class PersistenceSettings(StrictSettings):
    database_path: str | None = None
    migration_mode: Literal["apply", "validate"] = "apply"
    busy_timeout_ms: Annotated[int, Field(ge=0, le=30000)] = 1000

    @field_validator("database_path")
    @classmethod
    def local_database(cls, value: str | None) -> str | None:
        return absolute_local_path(value) if value is not None else None


class SessionSettings(StrictSettings):
    default_seed: Annotated[int, Field(ge=0, le=2**63 - 1)] = 0
    max_request_bytes: Annotated[int, Field(ge=256, le=65536)] = 4096


class ScenarioSettings(StrictSettings):
    directory: str | None = None
    validation: Literal["strict"] = "strict"

    @field_validator("directory")
    @classmethod
    def local_directory(cls, value: str | None) -> str | None:
        return absolute_local_path(value) if value is not None else None


class AppSettings(StrictSettings):
    schema_version: Literal["1.0"]
    api: ApiSettings
    paths: PathSettings
    logging: LoggingSettings
    features: FeatureSettings
    persistence: PersistenceSettings = PersistenceSettings()
    health: HealthSettings = HealthSettings()
    sessions: SessionSettings = SessionSettings()
    scenarios: ScenarioSettings = ScenarioSettings()

    def database_path(self) -> Path:
        """Resolve configuration only; never create or open storage."""
        return Path(
            self.persistence.database_path or str(Path(self.paths.data_root) / "sessions.sqlite3")
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> Self:
        try:
            return cls.model_validate_json(json.dumps(value, allow_nan=False))
        except ValidationError as error:
            details = "; ".join(
                f"{'.'.join(str(part) for part in item['loc'])}: {item['type']}"
                for item in error.errors(include_input=False, include_context=False)
            )
            raise ConfigurationError(f"Invalid configuration: {details}") from None
        except (TypeError, ValueError):
            raise ConfigurationError(
                "Invalid configuration: expected JSON-compatible values"
            ) from None

    def configuration_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def redacted_report(self) -> dict[str, object]:
        report: dict[str, object] = self.model_dump(mode="json")
        report["paths"] = {
            "data_root": "[REDACTED]",
            "model_root": "[REDACTED]" if self.paths.model_root is not None else None,
        }
        report["scenarios"] = {
            "directory": "[REDACTED]" if self.scenarios.directory else None,
            "validation": self.scenarios.validation,
        }
        report["configuration_hash"] = self.configuration_hash()
        report["logging"] = self.logging.model_dump(mode="json") | {
            "file_path": "[REDACTED]" if self.logging.file_path else None,
        }
        report["persistence"] = {
            "database_path": "[REDACTED]" if self.persistence.database_path is not None else None,
            "migration_mode": self.persistence.migration_mode,
            "busy_timeout_ms": self.persistence.busy_timeout_ms,
        }
        return report


class UniqueKeyLoader(yaml.SafeLoader):  # type: ignore[misc]
    def construct_mapping(self, node: Any, deep: bool = False) -> dict[str, object]:
        result: dict[str, object] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise ConfigurationError("Invalid YAML: duplicate or non-string key")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def read_yaml(text: str) -> dict[str, object]:
    try:
        result = yaml.load(text, Loader=UniqueKeyLoader)
    except (yaml.YAMLError, RecursionError, ValueError):
        raise ConfigurationError("Invalid configuration YAML") from None
    if not isinstance(result, dict):
        raise ConfigurationError("Invalid configuration YAML: expected a mapping")
    return result


def merge(base: dict[str, object], override: Mapping[str, object]) -> dict[str, object]:
    result = dict(base)
    for key, value in override.items():
        previous = result.get(key)
        if isinstance(previous, dict) and isinstance(value, dict):
            result[key] = merge(previous, value)
        else:
            result[key] = value
    return result


ENV_FIELDS = {
    "ATC_SCENARIOS_DIRECTORY": ("scenarios", "directory"),
    "ATC_SCENARIOS_VALIDATION": ("scenarios", "validation"),
    "ATC_SESSIONS_DEFAULT_SEED": ("sessions", "default_seed"),
    "ATC_SESSIONS_MAX_REQUEST_BYTES": ("sessions", "max_request_bytes"),
    "ATC_SCHEMA_VERSION": ("schema_version",),
    "ATC_API_HOST": ("api", "host"),
    "ATC_API_PORT": ("api", "port"),
    "ATC_API_CORS_ORIGINS": ("api", "cors_origins"),
    "ATC_PATHS_DATA_ROOT": ("paths", "data_root"),
    "ATC_PATHS_MODEL_ROOT": ("paths", "model_root"),
    "ATC_LOGGING_LEVEL": ("logging", "level"),
    "ATC_LOGGING_FILE_PATH": ("logging", "file_path"),
    "ATC_LOGGING_MAX_BYTES": ("logging", "max_bytes"),
    "ATC_LOGGING_BACKUP_COUNT": ("logging", "backup_count"),
    "ATC_HEALTH_TIMEOUT_SECONDS": ("health", "timeout_seconds"),
    "ATC_FEATURES_REPORT_CONFIGURATION": ("features", "report_configuration"),
    "ATC_PERSISTENCE_DATABASE_PATH": ("persistence", "database_path"),
    "ATC_PERSISTENCE_MIGRATION_MODE": ("persistence", "migration_mode"),
    "ATC_PERSISTENCE_BUSY_TIMEOUT_MS": ("persistence", "busy_timeout_ms"),
}
JSON_ENV_FIELDS = {
    "ATC_SESSIONS_DEFAULT_SEED",
    "ATC_SESSIONS_MAX_REQUEST_BYTES",
    "ATC_LOGGING_MAX_BYTES",
    "ATC_LOGGING_BACKUP_COUNT",
    "ATC_HEALTH_TIMEOUT_SECONDS",
    "ATC_API_PORT",
    "ATC_API_CORS_ORIGINS",
    "ATC_FEATURES_REPORT_CONFIGURATION",
    "ATC_PERSISTENCE_BUSY_TIMEOUT_MS",
}


def load_settings(
    config_file: Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    overrides: Mapping[str, object] | None = None,
) -> AppSettings:
    env = os.environ if environ is None else environ
    data = read_yaml(files(__package__).joinpath("defaults.yaml").read_text(encoding="utf-8"))
    if config_file is None and "ATC_CONFIG_FILE" in env:
        config_file = Path(env["ATC_CONFIG_FILE"])
    if config_file is not None:
        try:
            data = merge(data, read_yaml(config_file.read_text(encoding="utf-8")))
        except (OSError, UnicodeError):
            raise ConfigurationError("Cannot read configuration file") from None
    for name, raw in env.items():
        if not name.startswith("ATC_") or name == "ATC_CONFIG_FILE":
            continue
        if name not in ENV_FIELDS:
            raise ConfigurationError("Unknown ATC_ environment setting")
        value: object = raw
        if name in JSON_ENV_FIELDS or (
            name
            in {"ATC_PATHS_MODEL_ROOT", "ATC_PERSISTENCE_DATABASE_PATH", "ATC_LOGGING_FILE_PATH"}
            and raw == "null"
        ):
            try:
                value = json.loads(raw)
            except ValueError:
                raise ConfigurationError(f"Invalid environment setting: {name}") from None
        fields = ENV_FIELDS[name]
        layer: dict[str, object] = {fields[-1]: value}
        if len(fields) == 2:
            layer = {fields[0]: layer}
        data = merge(data, layer)
    data = merge(data, overrides or {})
    paths = data.get("paths")
    if isinstance(paths, dict):
        # Only the documented home shorthand is expanded. Relative paths remain invalid.
        for name in ("data_root", "model_root"):
            value = paths.get(name)
            if isinstance(value, str) and value.startswith("~/"):
                paths[name] = str(Path.home() / value[2:])
    return AppSettings.from_mapping(data)
