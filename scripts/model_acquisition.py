from __future__ import annotations

import json
import re
import shutil
import stat
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Protocol

from scripts.verify_model_zoo import Manifest, ModelEntry, sha256_file, verify_manifest

FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SAFE_COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
DEFAULT_LARGE_DOWNLOAD_BYTES = 1024**3
MINIMUM_SAFETY_MARGIN_BYTES = 1024**3
PRESERVATION_DIRECTORY = "PRESERVATION"


class AcquisitionError(RuntimeError):
    pass


class UnsafePathError(AcquisitionError):
    pass


class CollisionError(AcquisitionError):
    pass


class InsufficientStorageError(AcquisitionError):
    pass


class ConfirmationError(AcquisitionError):
    pass


class InterruptedAcquisition(AcquisitionError):
    pass


class TransientSourceError(AcquisitionError):
    pass


@dataclass(frozen=True)
class ResolvedSource:
    provider: str
    repository: str
    requested_revision: str
    immutable_revision: str
    canonical_uri: str
    expected_bytes: int | None
    cached_bytes: int = 0


class SourceProvider(Protocol):
    name: str

    def resolve(self, repository: str, revision: str, cache_root: Path) -> ResolvedSource: ...

    def fetch(self, source: ResolvedSource, destination: Path, cache_root: Path) -> None: ...


@dataclass(frozen=True)
class StorageReport:
    expected_bytes: int | None
    cached_bytes: int
    expected_download_bytes: int | None
    free_bytes: int
    safety_margin_bytes: int
    required_bytes: int | None


@dataclass(frozen=True)
class InventoryAsset:
    path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class AcquisitionResult:
    final_directory: Path
    candidate_manifest: Path
    inventory: tuple[InventoryAsset, ...]
    source: ResolvedSource
    storage: StorageReport


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def validate_component(value: str, label: str) -> str:
    if not SAFE_COMPONENT_PATTERN.fullmatch(value) or value in {".", ".."}:
        raise UnsafePathError(f"unsafe {label}: {value!r}")
    if PureWindowsPath(value).is_reserved():
        raise UnsafePathError(f"reserved Windows {label}: {value!r}")
    return value


def validate_upstream_relative_path(value: str) -> PurePosixPath:
    parts = value.split("/")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        not value
        or "\x00" in value
        or "\\" in value
        or any(part in {"", ".", ".."} for part in parts)
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or any(PureWindowsPath(part).is_reserved() for part in parts)
        or parts[0].casefold() == PRESERVATION_DIRECTORY.casefold()
    ):
        raise UnsafePathError(f"unsafe upstream path: {value!r}")
    return posix


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _reject_reparse_ancestry(path: Path, stop: Path | None = None) -> None:
    current = path
    while True:
        if current.is_symlink() or (current.exists() and _is_reparse_point(current)):
            raise UnsafePathError(f"symlink or reparse point is unsafe: {current}")
        if current == stop or current.parent == current:
            return
        current = current.parent


def validate_asset_root(asset_root: Path, repository_root: Path) -> Path:
    resolved_asset = asset_root.resolve(strict=True)
    resolved_repository = repository_root.resolve(strict=True)
    if not resolved_asset.is_dir():
        raise UnsafePathError("asset root is not a directory")
    if resolved_asset == Path(resolved_asset.anchor):
        raise UnsafePathError("asset root must not be a filesystem root")
    if _is_relative_to(resolved_asset, resolved_repository):
        raise UnsafePathError("asset root must be outside the Git repository")
    if _is_relative_to(resolved_repository, resolved_asset):
        raise UnsafePathError("asset root must not contain the Git repository")
    _reject_reparse_ancestry(resolved_asset)
    return resolved_asset


def storage_report(
    asset_root: Path,
    expected_bytes: int | None,
    cached_bytes: int,
    free_bytes: int | None = None,
) -> StorageReport:
    free = shutil.disk_usage(asset_root).free if free_bytes is None else free_bytes
    download = None if expected_bytes is None else max(0, expected_bytes - cached_bytes)
    margin = (
        MINIMUM_SAFETY_MARGIN_BYTES
        if expected_bytes is None
        else max(MINIMUM_SAFETY_MARGIN_BYTES, expected_bytes // 20)
    )
    required = (
        None
        if expected_bytes is None
        else expected_bytes + max(0, expected_bytes - cached_bytes) + margin
    )
    return StorageReport(expected_bytes, cached_bytes, download, free, margin, required)


def require_storage(report: StorageReport) -> None:
    if report.required_bytes is not None and report.free_bytes < report.required_bytes:
        raise InsufficientStorageError(
            f"insufficient storage: required={report.required_bytes} free={report.free_bytes}"
        )


def require_confirmation(
    report: StorageReport,
    assume_yes: bool,
    interactive: bool,
    confirm: Callable[[str], str],
    threshold: int = DEFAULT_LARGE_DOWNLOAD_BYTES,
) -> None:
    amount = report.expected_download_bytes
    if (amount is not None and amount < threshold) or assume_yes:
        return
    if not interactive:
        raise ConfirmationError("large or unknown download requires --yes in non-interactive mode")
    if confirm("Proceed with large or unknown acquisition? [y/N] ").strip().casefold() not in {
        "y",
        "yes",
    }:
        raise ConfirmationError("acquisition not confirmed")


def inventory_snapshot(files_root: Path) -> tuple[InventoryAsset, ...]:
    root = files_root.resolve(strict=True)
    assets: list[InventoryAsset] = []
    for candidate in sorted(files_root.rglob("*"), key=lambda item: item.as_posix()):
        relative = candidate.relative_to(files_root).as_posix()
        validate_upstream_relative_path(relative)
        if candidate.is_symlink() or _is_reparse_point(candidate):
            raise UnsafePathError(f"upstream snapshot contains a link/reparse point: {relative}")
        resolved = candidate.resolve(strict=True)
        if not _is_relative_to(resolved, root):
            raise UnsafePathError(f"upstream snapshot escapes staging: {relative}")
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise UnsafePathError(f"upstream snapshot contains a non-regular file: {relative}")
        assets.append(InventoryAsset(relative, candidate.stat().st_size, sha256_file(candidate)))
    if not assets:
        raise AcquisitionError("upstream snapshot is empty")
    return tuple(assets)


def _retry_fetch(
    provider: SourceProvider,
    source: ResolvedSource,
    destination: Path,
    cache_root: Path,
    attempts: int,
    sleep: Callable[[float], None],
) -> None:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    for attempt in range(1, attempts + 1):
        try:
            provider.fetch(source, destination, cache_root)
            return
        except KeyboardInterrupt as error:
            raise InterruptedAcquisition("acquisition interrupted") from error
        except (ConnectionError, TimeoutError, TransientSourceError):
            if attempt == attempts:
                raise
            sleep(float(2 ** (attempt - 1)))


def _candidate_entry(
    metadata: dict[str, object],
    source: ResolvedSource,
    inventory: Sequence[InventoryAsset],
    relative_revision: PurePosixPath,
    acquired_on: date,
) -> ModelEntry:
    data = dict(metadata)
    raw_identity = data.get("identity")
    if not isinstance(raw_identity, dict):
        raise AcquisitionError("metadata.identity must be an object")
    identity = dict(raw_identity)
    identity["revision"] = source.immutable_revision
    data["identity"] = identity
    data["source"] = {
        "publisher": data.pop("publisher"),
        "original_uri": source.canonical_uri,
    }
    data["acquisition"] = {
        "acquired_on": acquired_on,
        "method": f"{source.provider} snapshot pinned to immutable revision",
        "notes": str(data.pop("acquisition_notes", "")),
    }
    data["lifecycle"] = {
        "available": True,
        "benchmarked": False,
        "approved_for_runtime": False,
    }
    data["assets"] = [
        {
            "path": (relative_revision / PurePosixPath(asset.path)).as_posix(),
            "size_bytes": asset.size_bytes,
            "sha256": asset.sha256,
        }
        for asset in inventory
    ]
    return ModelEntry.model_validate(data)


def acquire(
    *,
    provider: SourceProvider,
    repository: str,
    revision: str,
    asset_root: Path,
    repository_root: Path,
    metadata: dict[str, object],
    assume_yes: bool = False,
    interactive: bool = False,
    confirm: Callable[[str], str] = input,
    threshold: int = DEFAULT_LARGE_DOWNLOAD_BYTES,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
    acquired_on: date | None = None,
    free_bytes: int | None = None,
    report_storage: Callable[[StorageReport], None] = lambda _: None,
) -> AcquisitionResult:
    root = validate_asset_root(asset_root, repository_root)
    cache_root = root / ".cache" / validate_component(provider.name, "provider")
    staging_root = root / ".staging"
    cache_root.mkdir(parents=True, exist_ok=True)
    staging_root.mkdir(parents=True, exist_ok=True)
    _reject_reparse_ancestry(cache_root, root)
    _reject_reparse_ancestry(staging_root, root)

    source = provider.resolve(repository, revision, cache_root)
    if not FULL_SHA_PATTERN.fullmatch(source.immutable_revision):
        raise AcquisitionError("provider did not resolve a full immutable commit SHA")

    category = validate_component(str(metadata["category"]), "category")
    publisher = validate_component(str(metadata["publisher"]), "publisher")
    identity = metadata.get("identity")
    if not isinstance(identity, dict):
        raise AcquisitionError("metadata.identity must be an object")
    model_name = validate_component(str(identity.get("name", "")), "model name")
    relative_revision = PurePosixPath(category, publisher, model_name, source.immutable_revision)
    final_directory = root.joinpath(*relative_revision.parts)
    if final_directory.exists():
        raise CollisionError(f"preserved revision already exists: {final_directory}")

    report = storage_report(root, source.expected_bytes, source.cached_bytes, free_bytes)
    report_storage(report)
    require_storage(report)
    require_confirmation(report, assume_yes, interactive, confirm, threshold)

    staging = staging_root / uuid.uuid4().hex
    preservation = staging / PRESERVATION_DIRECTORY
    staging.mkdir(parents=True)
    _retry_fetch(provider, source, staging, cache_root, attempts, sleep)
    inventory = inventory_snapshot(staging)
    entry = _candidate_entry(
        metadata, source, inventory, relative_revision, acquired_on or date.today()
    )
    staging_entry = entry.model_copy(
        update={
            "assets": [
                asset.model_copy(update={"path": item.path})
                for asset, item in zip(entry.assets, inventory, strict=True)
            ]
        }
    )
    staging_manifest = Manifest(
        schema_version="1.0", catalog_version="1.0.0", models=[staging_entry]
    )
    verification = verify_manifest(staging_manifest, staging)
    if not all(result.state.value == "VERIFIED" for result in verification):
        raise AcquisitionError("FP-001A verification rejected staged snapshot")

    preservation.mkdir()
    provenance = {
        "provider": source.provider,
        "repository": source.repository,
        "canonical_uri": source.canonical_uri,
        "requested_revision": source.requested_revision,
        "resolved_revision": source.immutable_revision,
        "expected_bytes": source.expected_bytes,
        "actual_bytes": sum(item.size_bytes for item in inventory),
    }
    candidate = Manifest(schema_version="1.0", catalog_version="1.0.0", models=[entry])
    (preservation / "acquisition.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (preservation / "inventory.json").write_text(
        json.dumps([asdict(item) for item in inventory], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (preservation / "candidate-manifest.json").write_text(
        candidate.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (preservation / "verification.json").write_text(
        json.dumps(
            [item.model_dump(mode="json") for item in verification], indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    final_directory.parent.mkdir(parents=True, exist_ok=True)
    if final_directory.exists():
        raise CollisionError(f"preserved revision already exists: {final_directory}")
    staging.rename(final_directory)
    return AcquisitionResult(
        final_directory,
        final_directory / PRESERVATION_DIRECTORY / "candidate-manifest.json",
        inventory,
        source,
        report,
    )
