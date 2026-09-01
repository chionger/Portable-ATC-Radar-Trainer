import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.verify_model_zoo import Manifest, load_manifest

ROOT = Path(__file__).resolve().parents[2]


def test_production_manifest_is_valid_and_preserves_lifecycle_boundaries() -> None:
    manifest = load_manifest(ROOT / "model-zoo/manifest.json")

    assert manifest.schema_version == "1.0"
    assert manifest.catalog_version == "1.0.0"
    assert all(entry.lifecycle.available for entry in manifest.models)
    assert all(not entry.lifecycle.benchmarked for entry in manifest.models)
    assert all(not entry.lifecycle.approved_for_runtime for entry in manifest.models)


def test_checked_in_schema_is_versioned_and_machine_readable() -> None:
    schema = json.loads((ROOT / "model-zoo/schemas/model-manifest.schema.json").read_text())

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema_version"] == {"const": "1.0"}
    assert set(schema["required"]) == {"schema_version", "catalog_version", "models"}
    assert schema["additionalProperties"] is False


def test_realistic_synthetic_fixture_manifest_is_valid() -> None:
    manifest = load_manifest(ROOT / "tests/fixtures/model-zoo/manifest.json")

    assert [entry.entry_id for entry in manifest.models] == [
        "synthetic-asr-verified",
        "synthetic-llm-missing",
        "synthetic-tts-mismatch",
    ]
    assert all(not entry.lifecycle.benchmarked for entry in manifest.models)
    assert all(not entry.lifecycle.approved_for_runtime for entry in manifest.models)


def test_incomplete_metadata_is_rejected() -> None:
    with pytest.raises(ValidationError, match="identity"):
        Manifest.model_validate(
            {
                "schema_version": "1.0",
                "catalog_version": "1.0.0",
                "models": [{"entry_id": "incomplete"}],
            }
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "2.0"),
        ("catalog_version", "latest"),
    ],
)
def test_invalid_manifest_versions_are_rejected(field: str, value: str) -> None:
    data = {"schema_version": "1.0", "catalog_version": "1.0.0", "models": []}
    data[field] = value

    with pytest.raises(ValidationError):
        Manifest.model_validate(data)


def test_unknown_manifest_metadata_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Manifest.model_validate(
            {"schema_version": "1.0", "catalog_version": "1.0.0", "models": [], "surprise": True}
        )
def _valid_model_entry() -> dict[str, object]:
    fixture = load_manifest(ROOT / "tests/fixtures/model-zoo/manifest.json")
    return fixture.models[0].model_dump(mode="python")


def test_model_entry_accepts_vision_category() -> None:
    entry = _valid_model_entry()
    entry["category"] = "VISION"

    manifest = Manifest.model_validate(
        {
            "schema_version": "1.0",
            "catalog_version": "1.0.0",
            "models": [entry],
        }
    )

    assert manifest.models[0].category == "VISION"


def test_checked_in_schema_supports_vision_category() -> None:
    schema = json.loads(
        (ROOT / "model-zoo/schemas/model-manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )

    categories = schema["$defs"]["model"]["properties"]["category"]["enum"]

    assert "VISION" in categories


def _external_inventory() -> dict[str, object]:
    return {
        "path": (
            "TTS/rhasspy/piper-voices/"
            "39ab474be869e9181350af6a65e4953eef67aaa0/"
            "PRESERVATION/inventory.json"
        ),
        "asset_count": 3292,
        "total_size_bytes": 11801416573,
        "sha256": "79c7bfcc7b1dcf2acc8fe56b85b8ccc0b29ec44b08cbe80cd457088100a72cb2",
    }


def test_model_entry_accepts_external_asset_inventory_instead_of_inline_assets() -> None:
    entry = _valid_model_entry()
    entry.pop("assets")
    entry["asset_inventory"] = _external_inventory()

    manifest = Manifest.model_validate(
        {
            "schema_version": "1.0",
            "catalog_version": "1.0.0",
            "models": [entry],
        }
    )

    assert manifest.models[0].asset_inventory is not None
    assert manifest.models[0].asset_inventory.asset_count == 3292


def test_model_entry_rejects_both_inline_assets_and_external_inventory() -> None:
    entry = _valid_model_entry()
    entry["asset_inventory"] = _external_inventory()

    with pytest.raises(ValidationError):
        Manifest.model_validate(
            {
                "schema_version": "1.0",
                "catalog_version": "1.0.0",
                "models": [entry],
            }
        )


def test_model_entry_rejects_missing_asset_representation() -> None:
    entry = _valid_model_entry()
    entry.pop("assets")

    with pytest.raises(ValidationError):
        Manifest.model_validate(
            {
                "schema_version": "1.0",
                "catalog_version": "1.0.0",
                "models": [entry],
            }
        )


def test_external_asset_inventory_rejects_invalid_sha256() -> None:
    entry = _valid_model_entry()
    entry.pop("assets")
    inventory = _external_inventory()
    inventory["sha256"] = "not-a-sha256"
    entry["asset_inventory"] = inventory

    with pytest.raises(ValidationError):
        Manifest.model_validate(
            {
                "schema_version": "1.0",
                "catalog_version": "1.0.0",
                "models": [entry],
            }
        )


def test_external_asset_inventory_rejects_unsafe_path() -> None:
    entry = _valid_model_entry()
    entry.pop("assets")
    inventory = _external_inventory()
    inventory["path"] = "../outside/inventory.json"
    entry["asset_inventory"] = inventory

    with pytest.raises(ValidationError):
        Manifest.model_validate(
            {
                "schema_version": "1.0",
                "catalog_version": "1.0.0",
                "models": [entry],
            }
        )

def test_external_asset_inventory_requires_preservation_inventory_path() -> None:
    entry = _valid_model_entry()
    entry.pop("assets")

    inventory = _external_inventory()
    inventory["path"] = "TTS/rhasspy/piper-voices/inventory.json"
    entry["asset_inventory"] = inventory

    with pytest.raises(ValidationError):
        Manifest.model_validate(
            {
                "schema_version": "1.0",
                "catalog_version": "1.0.0",
                "models": [entry],
            }
        )

def test_checked_in_schema_supports_external_asset_inventory() -> None:
    schema = json.loads(
        (
            ROOT / "model-zoo/schemas/model-manifest.schema.json"
        ).read_text(encoding="utf-8")
    )

    model_schema = schema["$defs"]["model"]

    assert "assets" not in model_schema["required"]

    assert model_schema["properties"]["assets"] == {
        "type": "array",
        "minItems": 1,
        "items": {"$ref": "#/$defs/asset"},
    }

    assert model_schema["properties"]["asset_inventory"] == {
        "$ref": "#/$defs/asset_inventory"
    }

    assert model_schema["oneOf"] == [
        {
            "required": ["assets"],
            "not": {"required": ["asset_inventory"]},
        },
        {
            "required": ["asset_inventory"],
            "not": {"required": ["assets"]},
        },
    ]

    inventory_schema = schema["$defs"]["asset_inventory"]

    assert inventory_schema["additionalProperties"] is False
    assert set(inventory_schema["required"]) == {
        "path",
        "asset_count",
        "total_size_bytes",
        "sha256",
    }

    assert (
        inventory_schema["properties"]["path"]["pattern"]
        == r"(^|.*/)PRESERVATION/inventory\.json$"
    )
    assert inventory_schema["properties"]["asset_count"]["minimum"] == 1
    assert inventory_schema["properties"]["total_size_bytes"]["minimum"] == 0
    assert (
        inventory_schema["properties"]["sha256"]["pattern"]
        == "^[0-9a-f]{64}$"
    )
