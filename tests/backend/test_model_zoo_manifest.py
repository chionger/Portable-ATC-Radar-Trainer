import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.verify_model_zoo import Manifest, load_manifest

ROOT = Path(__file__).resolve().parents[2]


def test_empty_production_manifest_is_valid() -> None:
    manifest = load_manifest(ROOT / "model-zoo/manifest.json")

    assert manifest == Manifest(schema_version="1.0", catalog_version="1.0.0", models=[])


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
