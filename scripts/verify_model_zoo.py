from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ENTRY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
CATALOG_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
HASH_CHUNK_SIZE = 1024 * 1024


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Identity(StrictModel):
    family: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    revision: Annotated[str, Field(min_length=1)]
    variant: Annotated[str, Field(min_length=1)]


class Source(StrictModel):
    publisher: Annotated[str, Field(min_length=1)]
    original_uri: Annotated[str, Field(min_length=1)]


class Acquisition(StrictModel):
    acquired_on: date
    method: Annotated[str, Field(min_length=1)]
    notes: str


class Licence(StrictModel):
    name: Annotated[str, Field(min_length=1)]
    spdx_id: str | None
    reference_uri: Annotated[str, Field(min_length=1)]
    usage_notes: str


class Lifecycle(StrictModel):
    available: bool
    benchmarked: bool
    approved_for_runtime: bool

    @model_validator(mode="after")
    def require_ordered_states(self) -> Lifecycle:
        if self.benchmarked and not self.available:
            raise ValueError("benchmarked requires available")
        if self.approved_for_runtime and not self.benchmarked:
            raise ValueError("approved_for_runtime requires benchmarked")
        return self


class Asset(StrictModel):
    path: Annotated[str, Field(min_length=1)]
    size_bytes: Annotated[int, Field(ge=0)]
    sha256: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        validate_relative_asset_path(value)
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value

class AssetInventory(StrictModel):
    path: Annotated[str, Field(min_length=1)]
    asset_count: Annotated[int, Field(ge=1)]
    total_size_bytes: Annotated[int, Field(ge=0)]
    sha256: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        validate_relative_asset_path(value)

        parts = PurePosixPath(value).parts
        if len(parts) < 2 or parts[-2:] != ("PRESERVATION", "inventory.json"):
            raise ValueError(
                "asset_inventory path must end with "
                "'PRESERVATION/inventory.json'"
            )

        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value


class ModelEntry(StrictModel):
    entry_id: str
    identity: Identity
    category: Literal["ASR", "LLM", "TTS", "VISION", "OTHER_LOCAL_AI"]
    intended_role: Annotated[str, Field(min_length=1)]
    format: Annotated[str, Field(min_length=1)]
    quantisation: Annotated[str, Field(min_length=1)] | None
    source: Source
    acquisition: Acquisition
    licence: Licence
    runtime_compatibility: list[Annotated[str, Field(min_length=1)]]
    lifecycle: Lifecycle
    assets: Annotated[list[Asset], Field(min_length=1)] | None = None
    asset_inventory: AssetInventory | None = None

    @field_validator("entry_id")
    @classmethod
    def validate_entry_id(cls, value: str) -> str:
        if not ENTRY_ID_PATTERN.fullmatch(value):
            raise ValueError("entry_id must contain lowercase letters, digits, '.', '_' or '-'")
        return value

    @model_validator(mode="after")
    def require_unique_values(self) -> ModelEntry:
        if (self.assets is None) == (self.asset_inventory is None):
            raise ValueError("exactly one of assets or asset_inventory must be provided")

        if self.assets is not None:
            paths = [asset.path for asset in self.assets]
            if len(paths) != len(set(paths)):
                raise ValueError("asset paths must be unique within an entry")

        if len(self.runtime_compatibility) != len(set(self.runtime_compatibility)):
            raise ValueError("runtime_compatibility values must be unique")

        return self


class Manifest(StrictModel):
    schema_version: Literal["1.0"]
    catalog_version: str
    models: list[ModelEntry]

    @field_validator("catalog_version")
    @classmethod
    def validate_catalog_version(cls, value: str) -> str:
        if not CATALOG_VERSION_PATTERN.fullmatch(value):
            raise ValueError("catalog_version must use MAJOR.MINOR.PATCH")
        return value

    @model_validator(mode="after")
    def require_unique_entries_and_paths(self) -> Manifest:
        entry_ids = [entry.entry_id for entry in self.models]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("entry_id values must be unique")

        paths: list[str] = []
        for entry in self.models:
            if entry.assets is not None:
                paths.extend(asset.path for asset in entry.assets)
            if entry.asset_inventory is not None:
                paths.append(entry.asset_inventory.path)

        if len(paths) != len(set(paths)):
            raise ValueError("asset paths must be unique across the manifest")

        return self


class VerificationState(StrEnum):
    VERIFIED = "VERIFIED"
    MISSING = "MISSING"
    HASH_MISMATCH = "HASH_MISMATCH"
    SIZE_MISMATCH = "SIZE_MISMATCH"
    UNSAFE_PATH = "UNSAFE_PATH"


class VerificationResult(StrictModel):
    entry_id: str
    path: str
    state: VerificationState
    expected_sha256: str
    actual_sha256: str | None = None
    detail: str | None = None


def validate_relative_asset_path(value: str) -> None:
    if "\x00" in value:
        raise ValueError("asset path contains a NUL character")
    if "\\" in value:
        raise ValueError("asset paths must use forward slashes")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("asset path must not contain empty, '.' or '..' segments")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise ValueError("asset path must be relative to the asset root")


def load_manifest(path: Path) -> Manifest:
    return Manifest.model_validate_json(path.read_text(encoding="utf-8"))


def resolve_asset_path(asset_root: Path, relative_path: str) -> Path:
    validate_relative_asset_path(relative_path)
    resolved_root = asset_root.resolve(strict=True)
    if not resolved_root.is_dir():
        raise ValueError("asset root is not a directory")
    candidate = resolved_root.joinpath(*PurePosixPath(relative_path).parts).resolve(strict=False)
    try:
        candidate.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError("resolved asset path escapes the asset root") from error
    return candidate


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(
    entry_id: str,
    asset_root: Path,
    asset_path: str,
    expected_sha256: str,
    expected_size: int | None = None,
) -> VerificationResult:
    try:
        candidate = resolve_asset_path(asset_root, asset_path)
    except (OSError, ValueError) as error:
        return VerificationResult(
            entry_id=entry_id,
            path=asset_path,
            state=VerificationState.UNSAFE_PATH,
            expected_sha256=expected_sha256,
            detail=str(error),
        )

    if not candidate.is_file():
        return VerificationResult(
            entry_id=entry_id,
            path=asset_path,
            state=VerificationState.MISSING,
            expected_sha256=expected_sha256,
        )

    actual_sha256 = sha256_file(candidate)

    if not hmac.compare_digest(actual_sha256, expected_sha256):
        state = VerificationState.HASH_MISMATCH
        detail = None
    elif expected_size is not None and os.path.getsize(candidate) != expected_size:
        state = VerificationState.SIZE_MISMATCH
        detail = (
            f"expected_size={expected_size} "
            f"actual_size={os.path.getsize(candidate)}"
        )
    else:
        state = VerificationState.VERIFIED
        detail = None

    return VerificationResult(
        entry_id=entry_id,
        path=asset_path,
        state=state,
        expected_sha256=expected_sha256,
        actual_sha256=actual_sha256,
        detail=detail,
    )


def verify_manifest(manifest: Manifest, asset_root: Path) -> list[VerificationResult]:
    results: list[VerificationResult] = []

    for entry in manifest.models:
        if entry.assets is not None:
            for asset in entry.assets:
                results.append(
                    verify_file(
                        entry_id=entry.entry_id,
                        asset_root=asset_root,
                        asset_path=asset.path,
                        expected_sha256=asset.sha256,
                        expected_size=asset.size_bytes,
                    )
                )

        if entry.asset_inventory is not None:
            inventory_result = verify_file(
                entry_id=entry.entry_id,
                asset_root=asset_root,
                asset_path=entry.asset_inventory.path,
                expected_sha256=entry.asset_inventory.sha256,
            )
            results.append(inventory_result)

            if inventory_result.state != VerificationState.VERIFIED:
                continue

            inventory_path = resolve_asset_path(
                asset_root,
                entry.asset_inventory.path,
            )

            try:
                inventory_data = json.loads(
                    inventory_path.read_text(encoding="utf-8")
                )

                if not isinstance(inventory_data, list):
                    raise TypeError(
                        "external inventory must be a JSON array"
                    )

                inventory_assets = [
                    Asset.model_validate(item)
                    for item in inventory_data
                ]
            except (
                json.JSONDecodeError,
                UnicodeDecodeError,
                ValidationError,
                TypeError,
            ) as error:
                results.append(
                    VerificationResult(
                        entry_id=entry.entry_id,
                        path=entry.asset_inventory.path,
                        state=VerificationState.UNSAFE_PATH,
                        expected_sha256=entry.asset_inventory.sha256,
                        actual_sha256=inventory_result.actual_sha256,
                        detail=str(error),
                    )
                )
                continue

            inventory_asset_paths = [
                asset.path for asset in inventory_assets
            ]
            if len(inventory_asset_paths) != len(set(inventory_asset_paths)):
                results.append(
                    VerificationResult(
                        entry_id=entry.entry_id,
                        path=entry.asset_inventory.path,
                        state=VerificationState.UNSAFE_PATH,
                        expected_sha256=entry.asset_inventory.sha256,
                        actual_sha256=inventory_result.actual_sha256,
                        detail=(
                            "asset paths must be unique within "
                            "external inventory"
                        ),
                    )
                )
                continue

            actual_asset_count = len(inventory_assets)
            if actual_asset_count != entry.asset_inventory.asset_count:
                results.append(
                    VerificationResult(
                        entry_id=entry.entry_id,
                        path=entry.asset_inventory.path,
                        state=VerificationState.SIZE_MISMATCH,
                        expected_sha256=entry.asset_inventory.sha256,
                        actual_sha256=inventory_result.actual_sha256,
                        detail=(
                            f"expected_asset_count="
                            f"{entry.asset_inventory.asset_count} "
                            f"actual_asset_count={actual_asset_count}"
                        ),
                    )
                )

            actual_total_size_bytes = sum(
                asset.size_bytes for asset in inventory_assets
            )
            if actual_total_size_bytes != entry.asset_inventory.total_size_bytes:
                results.append(
                    VerificationResult(
                        entry_id=entry.entry_id,
                        path=entry.asset_inventory.path,
                        state=VerificationState.SIZE_MISMATCH,
                        expected_sha256=entry.asset_inventory.sha256,
                        actual_sha256=inventory_result.actual_sha256,
                        detail=(
                            f"expected_total_size_bytes="
                            f"{entry.asset_inventory.total_size_bytes} "
                            f"actual_total_size_bytes={actual_total_size_bytes}"
                        ),
                    )
                )

            inventory_parts = PurePosixPath(entry.asset_inventory.path).parts
            model_root_parts = inventory_parts[:-2]

            for asset in inventory_assets:
                full_asset_path = PurePosixPath(
                    *model_root_parts,
                    *PurePosixPath(asset.path).parts,
                ).as_posix()

                results.append(
                    verify_file(
                        entry_id=entry.entry_id,
                        asset_root=asset_root,
                        asset_path=full_asset_path,
                        expected_sha256=asset.sha256,
                        expected_size=asset.size_bytes,
                    )
                )

    return results


def format_text(results: Sequence[VerificationResult]) -> str:
    lines: list[str] = []
    for result in results:
        line = f"{result.state.value} entry={result.entry_id} path={result.path}"
        if result.actual_sha256 is not None:
            line += (
                f" expected_sha256={result.expected_sha256} actual_sha256={result.actual_sha256}"
            )
        if result.detail is not None:
            line += f" detail={json.dumps(result.detail)}"
        lines.append(line)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and verify an offline model-zoo manifest."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--asset-root", required=True, type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        results = verify_manifest(manifest, args.asset_root)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(f"INVALID_MANIFEST {error}")
        return 2
    if args.as_json:
        print(
            json.dumps(
                [result.model_dump(mode="json") for result in results],
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    else:
        print(format_text(results))
    return 0 if all(result.state is VerificationState.VERIFIED for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
