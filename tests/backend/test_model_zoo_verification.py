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
