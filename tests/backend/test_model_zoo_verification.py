import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts.verify_model_zoo import (
    VerificationState,
    format_text,
    load_manifest,
    main,
    resolve_asset_path,
    sha256_file,
    validate_relative_asset_path,
    verify_manifest,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests/fixtures/model-zoo"
ASSET_ROOT = FIXTURE_ROOT / "assets"


def _external_inventory_manifest(
    inventory_path: str,
    inventory_sha256: str,
    asset_count: int,
    total_size_bytes: int,
):
    return {
        "schema_version": "1.0",
        "catalog_version": "1.0.0",
        "models": [
            {
                "entry_id": "synthetic-external-inventory",
                "identity": {
                    "family": "Synthetic Test Family",
                    "name": "Synthetic External Inventory Fixture",
                    "revision": "test-revision-external-001",
                    "variant": "deterministic-external-inventory-fixture",
                },
                "category": "ASR",
                "intended_role": "Verification test fixture",
                "format": "test-fixture",
                "quantisation": None,
                "source": {
                    "publisher": "test-suite",
                    "original_uri": "https://example.invalid/external-inventory",
                },
                "acquisition": {
                    "acquired_on": "2026-08-31",
                    "method": "synthetic-test",
                    "notes": "External inventory verification fixture",
                },
                "licence": {
                    "name": "Test fixture",
                    "spdx_id": None,
                    "reference_uri": "https://example.invalid/test-licence",
                    "usage_notes": "Test only",
                },
                "runtime_compatibility": [],
                "lifecycle": {
                    "available": True,
                    "benchmarked": False,
                    "approved_for_runtime": False,
                },
                "asset_inventory": {
                    "path": inventory_path,
                    "asset_count": asset_count,
                    "total_size_bytes": total_size_bytes,
                    "sha256": inventory_sha256,
                },
            }
        ],
    }


def test_known_sha256_calculation() -> None:
    fixture = ASSET_ROOT / "verified-fixture.dat"

    assert sha256_file(fixture) == hashlib.sha256(fixture.read_bytes()).hexdigest()
    assert (
        sha256_file(fixture) == "0c56c211c6c100a50860972f27db1b7ca32127be6f17da4a0fa30950edba32fb"
    )


def test_all_checked_in_asset_fixture_bytes_are_stable() -> None:
    expected = {
        "verified-fixture.dat": (
            33,
            "0c56c211c6c100a50860972f27db1b7ca32127be6f17da4a0fa30950edba32fb",
        ),
        "mismatch-fixture.dat": (
            35,
            "9e294c917abbff9cc7b781f75c572d6b7bab0d55031af0b066be2d8806bc068c",
        ),
    }
    actual = {
        path.name: (path.stat().st_size, sha256_file(path))
        for path in sorted(ASSET_ROOT.glob("*.dat"))
    }

    assert actual == expected


def test_fixture_integration_reports_all_required_states() -> None:
    results = verify_manifest(load_manifest(FIXTURE_ROOT / "manifest.json"), ASSET_ROOT)

    assert [result.state for result in results] == [
        VerificationState.VERIFIED,
        VerificationState.MISSING,
        VerificationState.HASH_MISMATCH,
    ]


def test_verification_output_is_deterministic() -> None:
    manifest = load_manifest(FIXTURE_ROOT / "manifest.json")

    first = format_text(verify_manifest(manifest, ASSET_ROOT))
    second = format_text(verify_manifest(manifest, ASSET_ROOT))

    assert first == second


def test_machine_output_is_deterministic(capsys: pytest.CaptureFixture[str]) -> None:
    arguments = [
        "--manifest",
        str(FIXTURE_ROOT / "manifest.json"),
        "--asset-root",
        str(ASSET_ROOT),
        "--json",
    ]

    assert main(arguments) == 1
    first = capsys.readouterr().out
    assert main(arguments) == 1
    second = capsys.readouterr().out

    assert first == second
    assert [item["state"] for item in json.loads(first)] == ["VERIFIED", "MISSING", "HASH_MISMATCH"]


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../escape.dat",
        "nested/../escape.dat",
        "/absolute.dat",
        "C:/drive-qualified.dat",
        "//server/share/model.dat",
        "nested\\windows.dat",
        "./dot.dat",
        "nul\x00byte.dat",
    ],
)
def test_unsafe_manifest_paths_are_rejected(unsafe_path: str) -> None:
    with pytest.raises(ValueError):
        validate_relative_asset_path(unsafe_path)


def test_misleading_sibling_prefix_is_not_under_root(tmp_path: Path) -> None:
    root = tmp_path / "models"
    root.mkdir()

    with pytest.raises(ValueError):
        resolve_asset_path(root, "../models-evil/model.dat")


def test_symlink_escape_is_rejected_when_supported(tmp_path: Path) -> None:
    root = tmp_path / "models"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "asset.dat").write_text("outside", encoding="utf-8")
    link = root / "linked"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are not available in this environment")

    with pytest.raises(ValueError, match="escapes"):
        resolve_asset_path(root, "linked/asset.dat")


def test_cli_rejects_invalid_manifest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"schema_version":"1.0"}', encoding="utf-8")

    assert main(["--manifest", str(invalid), "--asset-root", str(ASSET_ROOT)]) == 2
    assert capsys.readouterr().out.startswith("INVALID_MANIFEST ")

def test_external_inventory_verifies_listed_asset(tmp_path: Path) -> None:
    asset_root = tmp_path / "external-model-zoo"
    model_root = asset_root / "TTS" / "test" / "model" / "revision-001"
    preservation_dir = model_root / "PRESERVATION"
    preservation_dir.mkdir(parents=True)

    asset_path = model_root / "voice.onnx"
    asset_path.write_bytes(b"synthetic voice bytes")

    inventory_data = [
        {
            "path": "voice.onnx",
            "size_bytes": asset_path.stat().st_size,
            "sha256": sha256_file(asset_path),
        }
    ]

    inventory_path = preservation_dir / "inventory.json"
    inventory_path.write_text(
        json.dumps(inventory_data),
        encoding="utf-8",
    )

    manifest_data = _external_inventory_manifest(
        "TTS/test/model/revision-001/PRESERVATION/inventory.json",
        sha256_file(inventory_path),
        1,
        asset_path.stat().st_size,
    )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data),
        encoding="utf-8",
    )

    results = verify_manifest(load_manifest(manifest_path), asset_root)

    assert any(
        result.path == "TTS/test/model/revision-001/voice.onnx"
        and result.state == VerificationState.VERIFIED
        for result in results
    )

def test_external_inventory_is_verified_before_listed_assets(tmp_path: Path) -> None:
    asset_root = tmp_path / "external-model-zoo"
    model_root = asset_root / "TTS" / "test" / "model" / "revision-001"
    preservation_dir = model_root / "PRESERVATION"
    preservation_dir.mkdir(parents=True)

    asset_path = model_root / "voice.onnx"
    asset_path.write_bytes(b"synthetic voice bytes")

    inventory_data = [
        {
            "path": "voice.onnx",
            "size_bytes": asset_path.stat().st_size,
            "sha256": sha256_file(asset_path),
        }
    ]

    inventory_path = preservation_dir / "inventory.json"
    inventory_path.write_text(
        json.dumps(inventory_data),
        encoding="utf-8",
    )

    wrong_inventory_sha256 = "0" * 64
    assert sha256_file(inventory_path) != wrong_inventory_sha256

    manifest_data = _external_inventory_manifest(
        "TTS/test/model/revision-001/PRESERVATION/inventory.json",
        wrong_inventory_sha256,
        1,
        asset_path.stat().st_size,
    )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data),
        encoding="utf-8",
    )

    results = verify_manifest(load_manifest(manifest_path), asset_root)

    assert any(
        result.path
        == "TTS/test/model/revision-001/PRESERVATION/inventory.json"
        and result.state == VerificationState.HASH_MISMATCH
        for result in results
    )

    assert not any(
        result.path == "TTS/test/model/revision-001/voice.onnx"
        for result in results
    )

def test_external_inventory_detects_asset_count_mismatch(tmp_path: Path) -> None:
    asset_root = tmp_path / "external-model-zoo"
    model_root = asset_root / "TTS" / "test" / "model" / "revision-001"
    preservation_dir = model_root / "PRESERVATION"
    preservation_dir.mkdir(parents=True)

    asset_path = model_root / "voice.onnx"
    asset_path.write_bytes(b"synthetic voice bytes")

    inventory_data = [
        {
            "path": "voice.onnx",
            "size_bytes": asset_path.stat().st_size,
            "sha256": sha256_file(asset_path),
        }
    ]

    inventory_path = preservation_dir / "inventory.json"
    inventory_path.write_text(
        json.dumps(inventory_data),
        encoding="utf-8",
    )

    manifest_data = _external_inventory_manifest(
        "TTS/test/model/revision-001/PRESERVATION/inventory.json",
        sha256_file(inventory_path),
        2,
        asset_path.stat().st_size,
    )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data),
        encoding="utf-8",
    )

    results = verify_manifest(load_manifest(manifest_path), asset_root)

    assert any(
        result.path
        == "TTS/test/model/revision-001/PRESERVATION/inventory.json"
        and result.state == VerificationState.SIZE_MISMATCH
        and result.detail is not None
        and "expected_asset_count=2" in result.detail
        and "actual_asset_count=1" in result.detail
        for result in results
    )

def test_external_inventory_detects_total_size_mismatch(tmp_path: Path) -> None:
    asset_root = tmp_path / "external-model-zoo"
    model_root = asset_root / "TTS" / "test" / "model" / "revision-001"
    preservation_dir = model_root / "PRESERVATION"
    preservation_dir.mkdir(parents=True)

    asset_path = model_root / "voice.onnx"
    asset_path.write_bytes(b"synthetic voice bytes")

    inventory_data = [
        {
            "path": "voice.onnx",
            "size_bytes": asset_path.stat().st_size,
            "sha256": sha256_file(asset_path),
        }
    ]

    inventory_path = preservation_dir / "inventory.json"
    inventory_path.write_text(
        json.dumps(inventory_data),
        encoding="utf-8",
    )

    actual_total_size = asset_path.stat().st_size
    wrong_total_size = actual_total_size + 1

    manifest_data = _external_inventory_manifest(
        "TTS/test/model/revision-001/PRESERVATION/inventory.json",
        sha256_file(inventory_path),
        1,
        wrong_total_size,
    )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data),
        encoding="utf-8",
    )

    results = verify_manifest(load_manifest(manifest_path), asset_root)

    assert any(
        result.path
        == "TTS/test/model/revision-001/PRESERVATION/inventory.json"
        and result.state == VerificationState.SIZE_MISMATCH
        and result.detail is not None
        and f"expected_total_size_bytes={wrong_total_size}" in result.detail
        and f"actual_total_size_bytes={actual_total_size}" in result.detail
        for result in results
    )

def test_external_inventory_rejects_unsafe_asset_path(tmp_path: Path) -> None:
    asset_root = tmp_path / "external-model-zoo"
    model_root = asset_root / "TTS" / "test" / "model" / "revision-001"
    preservation_dir = model_root / "PRESERVATION"
    preservation_dir.mkdir(parents=True)

    inventory_data = [
        {
            "path": "../outside.dat",
            "size_bytes": 1,
            "sha256": "0" * 64,
        }
    ]

    inventory_path = preservation_dir / "inventory.json"
    inventory_path.write_text(
        json.dumps(inventory_data),
        encoding="utf-8",
    )

    manifest_data = _external_inventory_manifest(
        "TTS/test/model/revision-001/PRESERVATION/inventory.json",
        sha256_file(inventory_path),
        1,
        1,
    )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data),
        encoding="utf-8",
    )

    results = verify_manifest(load_manifest(manifest_path), asset_root)

    assert any(
        result.path
        == "TTS/test/model/revision-001/PRESERVATION/inventory.json"
        and result.state == VerificationState.UNSAFE_PATH
        for result in results
    )

def test_external_inventory_rejects_duplicate_asset_paths(tmp_path: Path) -> None:
    asset_root = tmp_path / "external-model-zoo"
    model_root = asset_root / "TTS" / "test" / "model" / "revision-001"
    preservation_dir = model_root / "PRESERVATION"
    preservation_dir.mkdir(parents=True)

    asset_path = model_root / "voice.onnx"
    asset_path.write_bytes(b"synthetic voice bytes")

    asset_record = {
        "path": "voice.onnx",
        "size_bytes": asset_path.stat().st_size,
        "sha256": sha256_file(asset_path),
    }

    inventory_data = [
        asset_record,
        dict(asset_record),
    ]

    inventory_path = preservation_dir / "inventory.json"
    inventory_path.write_text(
        json.dumps(inventory_data),
        encoding="utf-8",
    )

    manifest_data = _external_inventory_manifest(
        "TTS/test/model/revision-001/PRESERVATION/inventory.json",
        sha256_file(inventory_path),
        2,
        asset_path.stat().st_size * 2,
    )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data),
        encoding="utf-8",
    )

    results = verify_manifest(load_manifest(manifest_path), asset_root)

    assert any(
        result.path
        == "TTS/test/model/revision-001/PRESERVATION/inventory.json"
        and result.state == VerificationState.UNSAFE_PATH
        and result.detail is not None
        and "asset paths must be unique" in result.detail
        for result in results
    )

def test_external_inventory_detects_missing_asset(tmp_path: Path) -> None:
    asset_root = tmp_path / "external-model-zoo"
    model_root = asset_root / "TTS" / "test" / "model" / "revision-001"
    preservation_dir = model_root / "PRESERVATION"
    preservation_dir.mkdir(parents=True)

    inventory_data = [
        {
            "path": "missing.onnx",
            "size_bytes": 123,
            "sha256": "0" * 64,
        }
    ]

    inventory_path = preservation_dir / "inventory.json"
    inventory_path.write_text(
        json.dumps(inventory_data),
        encoding="utf-8",
    )

    manifest_data = _external_inventory_manifest(
        "TTS/test/model/revision-001/PRESERVATION/inventory.json",
        sha256_file(inventory_path),
        1,
        123,
    )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data),
        encoding="utf-8",
    )

    results = verify_manifest(load_manifest(manifest_path), asset_root)

    assert any(
        result.path == "TTS/test/model/revision-001/missing.onnx"
        and result.state == VerificationState.MISSING
        for result in results
    )

def test_external_inventory_detects_corrupted_asset(tmp_path: Path) -> None:
    asset_root = tmp_path / "external-model-zoo"
    model_root = asset_root / "TTS" / "test" / "model" / "revision-001"
    preservation_dir = model_root / "PRESERVATION"
    preservation_dir.mkdir(parents=True)

    asset_path = model_root / "voice.onnx"

    expected_bytes = b"1234567"
    corrupted_bytes = b"7654321"

    assert len(expected_bytes) == len(corrupted_bytes)

    expected_sha256 = hashlib.sha256(expected_bytes).hexdigest()

    asset_path.write_bytes(corrupted_bytes)

    inventory_data = [
        {
            "path": "voice.onnx",
            "size_bytes": len(expected_bytes),
            "sha256": expected_sha256,
        }
    ]

    inventory_path = preservation_dir / "inventory.json"
    inventory_path.write_text(
        json.dumps(inventory_data),
        encoding="utf-8",
    )

    manifest_data = _external_inventory_manifest(
        "TTS/test/model/revision-001/PRESERVATION/inventory.json",
        sha256_file(inventory_path),
        1,
        len(expected_bytes),
    )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data),
        encoding="utf-8",
    )

    results = verify_manifest(load_manifest(manifest_path), asset_root)

    assert any(
        result.path == "TTS/test/model/revision-001/voice.onnx"
        and result.state == VerificationState.HASH_MISMATCH
        for result in results
    )

def test_external_inventory_rejects_malformed_json(tmp_path: Path) -> None:
    asset_root = tmp_path / "external-model-zoo"
    model_root = asset_root / "TTS" / "test" / "model" / "revision-001"
    preservation_dir = model_root / "PRESERVATION"
    preservation_dir.mkdir(parents=True)

    inventory_path = preservation_dir / "inventory.json"
    inventory_path.write_text(
        '[{"path": "voice.onnx",',
        encoding="utf-8",
    )

    manifest_data = _external_inventory_manifest(
        "TTS/test/model/revision-001/PRESERVATION/inventory.json",
        sha256_file(inventory_path),
        1,
        1,
    )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data),
        encoding="utf-8",
    )

    results = verify_manifest(load_manifest(manifest_path), asset_root)

    assert any(
        result.path
        == "TTS/test/model/revision-001/PRESERVATION/inventory.json"
        and result.state == VerificationState.UNSAFE_PATH
        and result.detail is not None
        for result in results
    )

def test_external_inventory_rejects_non_array_json(tmp_path: Path) -> None:
    asset_root = tmp_path / "external-model-zoo"
    model_root = asset_root / "TTS" / "test" / "model" / "revision-001"
    preservation_dir = model_root / "PRESERVATION"
    preservation_dir.mkdir(parents=True)

    inventory_path = preservation_dir / "inventory.json"
    inventory_path.write_text(
        json.dumps(
            {
                "path": "voice.onnx",
                "size_bytes": 1,
                "sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )

    manifest_data = _external_inventory_manifest(
        "TTS/test/model/revision-001/PRESERVATION/inventory.json",
        sha256_file(inventory_path),
        1,
        1,
    )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data),
        encoding="utf-8",
    )

    results = verify_manifest(load_manifest(manifest_path), asset_root)

    assert any(
        result.path
        == "TTS/test/model/revision-001/PRESERVATION/inventory.json"
        and result.state == VerificationState.UNSAFE_PATH
        and result.detail is not None
        and "external inventory must be a JSON array" in result.detail
        for result in results
    )

def test_external_inventory_rejects_invalid_utf8_without_crashing(
    tmp_path: Path,
) -> None:
    asset_root = tmp_path / "external-model-zoo"
    model_root = asset_root / "TTS" / "test" / "model" / "revision-001"
    preservation_dir = model_root / "PRESERVATION"
    preservation_dir.mkdir(parents=True)

    inventory_path = preservation_dir / "inventory.json"
    inventory_path.write_bytes(b"\xff\xfe\xfa")

    manifest_data = _external_inventory_manifest(
        "TTS/test/model/revision-001/PRESERVATION/inventory.json",
        sha256_file(inventory_path),
        1,
        1,
    )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_data),
        encoding="utf-8",
    )

    results = verify_manifest(load_manifest(manifest_path), asset_root)

    assert any(
        result.path
        == "TTS/test/model/revision-001/PRESERVATION/inventory.json"
        and result.state == VerificationState.UNSAFE_PATH
        and result.detail is not None
        for result in results
    )
