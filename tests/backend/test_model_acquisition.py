import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from scripts.model_acquisition import (
    DEFAULT_LARGE_DOWNLOAD_BYTES,
    AcquisitionError,
    CollisionError,
    ConfirmationError,
    InsufficientStorageError,
    InterruptedAcquisition,
    ResolvedSource,
    UnsafePathError,
    acquire,
    inventory_snapshot,
    require_confirmation,
    storage_report,
    validate_asset_root,
    validate_upstream_relative_path,
)
from scripts.verify_model_zoo import load_manifest, verify_manifest

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40


@dataclass
class FakeProvider:
    failures: list[BaseException] | None = None
    name: str = "local-test"
    fetch_calls: int = 0

    def resolve(self, repository: str, revision: str, cache_root: Path) -> ResolvedSource:
        return ResolvedSource(
            provider=self.name,
            repository=repository,
            requested_revision=revision,
            immutable_revision=SHA,
            canonical_uri="urn:test:repository",
            expected_bytes=12,
        )

    def fetch(self, source: ResolvedSource, destination: Path, cache_root: Path) -> None:
        self.fetch_calls += 1
        if self.failures:
            error = self.failures.pop(0)
            raise error
        (cache_root / "provider.cache").write_text("cache", encoding="utf-8")
        source_fixture = ROOT / "tests" / "fixtures" / "model-acquisition" / "source-repository"
        shutil.copytree(source_fixture, destination, dirs_exist_ok=True)


def metadata() -> dict[str, object]:
    path = ROOT / "tests" / "fixtures" / "model-acquisition" / "catalogue-metadata.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def run_acquisition(tmp_path: Path, provider: FakeProvider | None = None):
    asset_root = tmp_path / "external-model-zoo"
    asset_root.mkdir(parents=True)
    result = acquire(
        provider=provider or FakeProvider(),
        repository="test/tiny-model",
        revision="main",
        asset_root=asset_root,
        repository_root=ROOT,
        metadata=metadata(),
        assume_yes=True,
        acquired_on=date(2026, 8, 23),
        free_bytes=10 * 1024**3,
        sleep=lambda _: None,
    )
    return asset_root, result


def test_synthetic_acquisition_uses_canonical_layout_and_verifies(tmp_path: Path) -> None:
    asset_root, result = run_acquisition(tmp_path)

    expected = asset_root / "ASR" / "Test-Publisher" / "tiny-model" / SHA
    assert result.final_directory == expected
    assert json.loads((expected / "config.json").read_text(encoding="utf-8")) == {
        "fixture": "FP-001B"
    }
    assert b"not real model weights" in (expected / "nested" / "weights.dat").read_bytes()
    assert not (expected / "files").exists()
    candidate = load_manifest(result.candidate_manifest)
    verification = verify_manifest(candidate, asset_root)
    assert all(item.state.value == "VERIFIED" for item in verification)


def test_candidate_manifest_defaults_and_provenance(tmp_path: Path) -> None:
    _, result = run_acquisition(tmp_path)
    candidate = load_manifest(result.candidate_manifest)
    entry = candidate.models[0]

    assert entry.identity.revision == SHA
    assert entry.lifecycle.available is True
    assert entry.lifecycle.benchmarked is False
    assert entry.lifecycle.approved_for_runtime is False
    provenance = json.loads(
        (result.final_directory / "PRESERVATION" / "acquisition.json").read_text()
    )
    assert provenance["requested_revision"] == "main"
    assert provenance["resolved_revision"] == SHA


def test_inventory_is_deterministic_and_excludes_local_data(tmp_path: Path) -> None:
    _, result = run_acquisition(tmp_path)

    assert [item.path for item in result.inventory] == ["config.json", "nested/weights.dat"]
    inventory = json.loads(
        (result.final_directory / "PRESERVATION" / "inventory.json").read_text()
    )
    assert [item["path"] for item in inventory] == ["config.json", "nested/weights.dat"]
    assert not any("PRESERVATION" in item["path"] for item in inventory)
    assert not any(".cache" in item["path"] or ".staging" in item["path"] for item in inventory)


def test_generated_candidate_and_inventory_are_deterministic(tmp_path: Path) -> None:
    _, first = run_acquisition(tmp_path / "first")
    _, second = run_acquisition(tmp_path / "second")

    assert first.candidate_manifest.read_bytes() == second.candidate_manifest.read_bytes()
    assert (
        first.final_directory / "PRESERVATION" / "inventory.json"
    ).read_bytes() == (second.final_directory / "PRESERVATION" / "inventory.json").read_bytes()


def test_existing_revision_collision_never_overwrites(tmp_path: Path) -> None:
    asset_root, result = run_acquisition(tmp_path)
    marker = result.final_directory / "config.json"

    with pytest.raises(CollisionError):
        acquire(
            provider=FakeProvider(),
            repository="test/tiny-model",
            revision="main",
            asset_root=asset_root,
            repository_root=ROOT,
            metadata=metadata(),
            assume_yes=True,
            free_bytes=10 * 1024**3,
        )
    assert json.loads(marker.read_text(encoding="utf-8")) == {"fixture": "FP-001B"}


def test_interruption_leaves_no_final_revision(tmp_path: Path) -> None:
    asset_root = tmp_path / "external"
    asset_root.mkdir()
    with pytest.raises(InterruptedAcquisition):
        acquire(
            provider=FakeProvider(failures=[KeyboardInterrupt()]),
            repository="test/tiny-model",
            revision="main",
            asset_root=asset_root,
            repository_root=ROOT,
            metadata=metadata(),
            assume_yes=True,
            free_bytes=10 * 1024**3,
        )
    assert not (asset_root / "ASR").exists()
    assert list((asset_root / ".staging").iterdir())


def test_transient_failures_are_bounded_and_retried(tmp_path: Path) -> None:
    provider = FakeProvider(failures=[ConnectionError(), TimeoutError()])
    _, result = run_acquisition(tmp_path, provider)

    assert result.final_directory.exists()
    assert provider.fetch_calls == 3


def test_non_transient_failure_is_not_retried(tmp_path: Path) -> None:
    provider = FakeProvider(failures=[ValueError("invalid")])
    asset_root = tmp_path / "external"
    asset_root.mkdir()
    with pytest.raises(ValueError, match="invalid"):
        acquire(
            provider=provider,
            repository="test/tiny-model",
            revision="main",
            asset_root=asset_root,
            repository_root=ROOT,
            metadata=metadata(),
            assume_yes=True,
            free_bytes=10 * 1024**3,
        )
    assert provider.fetch_calls == 1


def test_invalid_immutable_revision_is_rejected(tmp_path: Path) -> None:
    class BadRevisionProvider(FakeProvider):
        def resolve(self, repository: str, revision: str, cache_root: Path) -> ResolvedSource:
            resolved = super().resolve(repository, revision, cache_root)
            return ResolvedSource(**{**resolved.__dict__, "immutable_revision": "main"})

    asset_root = tmp_path / "external"
    asset_root.mkdir()
    with pytest.raises(AcquisitionError, match="full immutable"):
        acquire(
            provider=BadRevisionProvider(),
            repository="test/tiny-model",
            revision="main",
            asset_root=asset_root,
            repository_root=ROOT,
            metadata=metadata(),
            assume_yes=True,
        )


@pytest.mark.parametrize(
    "path",
    [
        "../escape",
        "nested/../escape",
        "/absolute",
        "C:/drive",
        "//server/share",
        "a\\b",
        "PRESERVATION/file",
    ],
)
def test_unsafe_upstream_paths_are_rejected(path: str) -> None:
    with pytest.raises(UnsafePathError):
        validate_upstream_relative_path(path)


def test_asset_root_inside_repository_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError, match="outside"):
        validate_asset_root(ROOT / "tests", ROOT)


def test_empty_snapshot_is_rejected(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(AcquisitionError, match="empty"):
        inventory_snapshot(empty)


def test_insufficient_storage_is_rejected_before_fetch(tmp_path: Path) -> None:
    asset_root = tmp_path / "external"
    asset_root.mkdir()
    provider = FakeProvider()
    with pytest.raises(InsufficientStorageError):
        acquire(
            provider=provider,
            repository="test/tiny-model",
            revision="main",
            asset_root=asset_root,
            repository_root=ROOT,
            metadata=metadata(),
            assume_yes=True,
            free_bytes=1,
        )
    assert provider.fetch_calls == 0


def test_large_download_requires_confirmation_and_yes_bypasses(tmp_path: Path) -> None:
    report = storage_report(tmp_path, DEFAULT_LARGE_DOWNLOAD_BYTES, 0, 10 * 1024**3)
    with pytest.raises(ConfirmationError):
        require_confirmation(report, False, False, input)
    require_confirmation(report, True, False, input)
    with pytest.raises(ConfirmationError, match="not confirmed"):
        require_confirmation(report, False, True, lambda _: "no")
