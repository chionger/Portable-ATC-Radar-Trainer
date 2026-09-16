import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from packages.infrastructure.configuration import AppSettings, ConfigurationError, load_settings
from scripts.run_api import main


def test_packaged_defaults_work_without_model_storage() -> None:
    settings = load_settings(environ={})
    assert settings.api.host == "127.0.0.1"
    assert settings.api.port == 8000
    assert settings.paths.model_root is None
    assert Path(settings.paths.data_root).is_absolute()
    assert settings.logging.level == "INFO"
    assert settings.features.report_configuration is False


def test_precedence_and_partial_group_merging(tmp_path: Path) -> None:
    local = tmp_path / "local.yaml"
    local.write_text("api:\n  port: 8100\nlogging:\n  level: DEBUG\n", encoding="utf-8")
    assert load_settings(local, environ={}).api.port == 8100
    env = {"ATC_CONFIG_FILE": str(local), "ATC_API_PORT": "8200"}
    assert load_settings(environ=env).api.port == 8200
    settings = load_settings(environ=env, overrides={"api": {"port": 8300}})
    assert settings.api.port == 8300
    assert settings.api.host == "127.0.0.1"
    assert settings.logging.level == "DEBUG"


def test_explicit_file_takes_precedence_over_environment_file(tmp_path: Path) -> None:
    local = tmp_path / "local.yaml"
    local.write_text("api:\n  port: 8100\n", encoding="utf-8")
    assert load_settings(local, environ={"ATC_CONFIG_FILE": "missing"}).api.port == 8100


@pytest.mark.parametrize("value", ["0", "65536", "true", '"8000"', "1.5", "null", "oops"])
def test_invalid_environment_port_is_rejected(value: str) -> None:
    with pytest.raises(ConfigurationError, match="api.port|ATC_API_PORT"):
        load_settings(environ={"ATC_API_PORT": value})


@pytest.mark.parametrize("value", ["yes", "1", '"false"'])
def test_feature_flag_requires_a_boolean(value: str) -> None:
    with pytest.raises(ConfigurationError):
        load_settings(environ={"ATC_FEATURES_REPORT_CONFIGURATION": value})


def test_unknown_yaml_and_environment_settings_are_rejected(tmp_path: Path) -> None:
    local = tmp_path / "local.yaml"
    local.write_text("api:\n  typo: 9000\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="api.typo"):
        load_settings(local, environ={})
    with pytest.raises(ConfigurationError, match="Unknown"):
        load_settings(environ={"ATC_API_PORRT": "9000"})


@pytest.mark.parametrize(
    "content", ["[]", "null", "api: [", "api: {}\napi: {}", "!!python/object:os {}"]
)
def test_invalid_yaml_is_rejected(tmp_path: Path, content: str) -> None:
    local = tmp_path / "bad.yaml"
    local.write_text(content, encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_settings(local, environ={})


def test_missing_file_and_invalid_utf8_are_reported_safely(tmp_path: Path) -> None:
    local = tmp_path / "private-name.yaml"
    with pytest.raises(ConfigurationError) as error:
        load_settings(local, environ={})
    assert "private-name" not in str(error.value)
    local.write_bytes(b"\xff")
    with pytest.raises(ConfigurationError, match="Cannot read"):
        load_settings(local, environ={})


@pytest.mark.parametrize(
    "value",
    [
        "relative/data",
        "C:relative",
        "C:/",
        "C:/data/../models",
        "//server/share",
        "\\\\?\\C:\\models",
        "C:/NUL/models",
        "C:/models:stream",
        "C:/trailing./data",
        "C:/bad?name",
    ],
)
def test_unsafe_model_paths_are_rejected_without_access(value: str) -> None:
    with pytest.raises(ConfigurationError, match="paths.model_root"):
        load_settings(environ={"ATC_PATHS_MODEL_ROOT": value})


def test_windows_paths_are_lexical_and_storage_is_not_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("must not probe storage")

    monkeypatch.setattr(Path, "exists", forbidden)
    monkeypatch.setattr(Path, "resolve", forbidden)
    settings = load_settings(environ={"ATC_PATHS_MODEL_ROOT": "Z:/offline/models"})
    assert settings.paths.model_root == "Z:\\offline\\models"


def test_paths_and_bad_values_are_redacted(tmp_path: Path) -> None:
    marker = "private-value-12345"
    settings = load_settings(environ={"ATC_PATHS_DATA_ROOT": f"C:/{marker}/data"})
    assert marker not in json.dumps(settings.redacted_report())
    assert settings.redacted_report()["paths"] == {
        "data_root": "[REDACTED]",
        "model_root": None,
    }
    local = tmp_path / "private.yaml"
    local.write_text(f"logging:\n  level: {marker}\n", encoding="utf-8")
    with pytest.raises(ConfigurationError) as error:
        load_settings(local, environ={})
    assert "logging.level" in str(error.value)
    assert marker not in str(error.value)


def test_hash_is_stable_across_order_and_source_and_changes_with_settings(tmp_path: Path) -> None:
    settings = load_settings(environ={"ATC_API_PORT": "8100"})
    local = tmp_path / "local.yaml"
    local.write_text("api:\n  port: 8100\n", encoding="utf-8")
    assert settings.configuration_hash() == load_settings(local, environ={}).configuration_hash()
    reordered = dict(reversed(list(settings.model_dump(mode="json").items())))
    assert AppSettings.from_mapping(reordered).configuration_hash() == settings.configuration_hash()
    assert len(settings.configuration_hash()) == 64
    assert settings.configuration_hash() != load_settings(environ={}).configuration_hash()


def test_cli_report_and_invalid_input_do_not_start_server(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run = Mock()
    monkeypatch.setattr("scripts.run_api.uvicorn.run", run)
    assert main(["--port", "8123", "--show-config"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["api"]["port"] == 8123
    assert report["paths"]["data_root"] == "[REDACTED]"
    assert main(["--port", "0"]) == 2
    assert "api.port" in capsys.readouterr().out
    run.assert_not_called()


def test_cli_passes_effective_settings_to_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock()
    monkeypatch.setattr("scripts.run_api.uvicorn.run", run)
    monkeypatch.setenv("ATC_API_PORT", "invalid-overridden-value")
    # Valid lower layers are required even when a later layer overrides them.
    assert main(["--port", "8123"]) == 2
    monkeypatch.setenv("ATC_API_PORT", "8100")
    assert main(["--port", "8123"]) == 0
    assert run.call_args.kwargs["port"] == 8123
    assert run.call_args.args[0].state.settings.api.port == 8123


def test_dev_url_uses_effective_port_and_ipv6_brackets(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--host", "::1", "--port", "8123", "--dev-web"]) == 0
    assert capsys.readouterr().out.strip() == "http://[::1]:8123"


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://remote.example",
        "http://localhost:70000",
        "http://localhost/path",
        "http://secret@localhost",
        "http://localhost?secret=value",
    ],
)
def test_unsafe_cors_origins_are_rejected(origin: str) -> None:
    with pytest.raises(ConfigurationError, match="api.cors_origins"):
        load_settings(environ={"ATC_API_CORS_ORIGINS": json.dumps([origin])})


def test_unsupported_schema_and_non_loopback_bind_are_rejected() -> None:
    with pytest.raises(ConfigurationError, match="schema_version"):
        load_settings(environ={"ATC_SCHEMA_VERSION": "2.0"})
    with pytest.raises(ConfigurationError, match="api.host"):
        load_settings(environ={"ATC_API_HOST": "0.0.0.0"})


def test_model_path_can_be_cleared_and_reported_without_leaking() -> None:
    settings = load_settings(environ={"ATC_PATHS_MODEL_ROOT": "Z:/private-models"})
    assert "private-models" not in json.dumps(settings.redacted_report())
    assert load_settings(environ={"ATC_PATHS_MODEL_ROOT": "null"}).paths.model_root is None


def test_hash_changes_when_private_path_changes() -> None:
    first = load_settings(environ={"ATC_PATHS_DATA_ROOT": "C:/data-one"})
    second = load_settings(environ={"ATC_PATHS_DATA_ROOT": "C:/data-two"})
    assert first.configuration_hash() != second.configuration_hash()


def test_settings_are_immutable() -> None:
    from pydantic import ValidationError

    settings = load_settings(environ={})
    with pytest.raises(ValidationError, match="frozen"):
        settings.api.port = 8123
