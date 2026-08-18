from pathlib import Path

from scripts.check_model_assets import (
    MAX_MODEL_ZOO_METADATA_BYTES,
    MAX_TINY_FIXTURE_BYTES,
    violations,
)

ROOT = Path(__file__).resolve().parents[2]


def test_current_tracked_files_contain_no_model_assets() -> None:
    assert violations(ROOT) == []


def test_recognized_model_weight_extensions_are_rejected() -> None:
    failures = violations(ROOT, ["somewhere/candidate.gguf", "elsewhere/weights.safetensors"])

    assert failures == [
        "elsewhere/weights.safetensors: recognized model-weight extension is forbidden",
        "somewhere/candidate.gguf: recognized model-weight extension is forbidden",
    ]


def test_model_zoo_asset_and_staging_directories_are_rejected() -> None:
    failures = violations(ROOT, ["model-zoo/assets/weights.bin", "model-zoo/staging/candidate.dat"])

    assert "model-zoo/assets/weights.bin: binary model-zoo asset is forbidden" in failures
    assert (
        "model-zoo/assets/weights.bin: model asset/staging/cache directory is forbidden" in failures
    )
    assert (
        "model-zoo/staging/candidate.dat: model asset/staging/cache directory is forbidden"
        in failures
    )


def test_generic_bin_is_scoped_instead_of_rejected_repository_wide() -> None:
    assert violations(ROOT, ["tests/fixtures/audio/example.bin"]) == []
    assert violations(ROOT, ["model-zoo/candidate.bin"]) == [
        "model-zoo/candidate.bin: binary model-zoo asset is forbidden"
    ]


def test_tiny_model_zoo_fixture_is_explicitly_permitted() -> None:
    assert violations(ROOT, ["tests/fixtures/model-zoo/assets/verified-fixture.dat"]) == []


def test_oversized_model_zoo_fixture_is_rejected(tmp_path: Path) -> None:
    fixture = tmp_path / "tests/fixtures/model-zoo/assets/too-large.dat"
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(b"x" * (MAX_TINY_FIXTURE_BYTES + 1))

    expected = (
        "tests/fixtures/model-zoo/assets/too-large.dat: "
        f"model-zoo fixture exceeds {MAX_TINY_FIXTURE_BYTES} bytes"
    )
    assert violations(tmp_path, ["tests/fixtures/model-zoo/assets/too-large.dat"]) == [expected]


def test_suspiciously_large_production_model_zoo_file_is_rejected(tmp_path: Path) -> None:
    suspicious = tmp_path / "model-zoo/unexpected.dat"
    suspicious.parent.mkdir(parents=True)
    suspicious.write_bytes(b"x" * (MAX_MODEL_ZOO_METADATA_BYTES + 1))

    assert violations(tmp_path, ["model-zoo/unexpected.dat"]) == [
        "model-zoo/unexpected.dat: suspiciously large file is forbidden in model-zoo metadata"
    ]
