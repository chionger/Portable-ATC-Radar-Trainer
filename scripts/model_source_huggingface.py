from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import httpx

from scripts.model_acquisition import (
    ResolvedSource,
    TransientSourceError,
    UnsafePathError,
    validate_upstream_relative_path,
)


class HuggingFaceSourceProvider:
    name = "huggingface"

    def __init__(self, api: Any | None = None, snapshot_download_fn: Any | None = None) -> None:
        if api is None or snapshot_download_fn is None:
            try:
                from huggingface_hub import HfApi, snapshot_download
            except ImportError as error:
                raise RuntimeError(
                    "Hugging Face acquisition requires installation with .[acquisition]"
                ) from error
            api = HfApi() if api is None else api
            snapshot_download_fn = (
                snapshot_download if snapshot_download_fn is None else snapshot_download_fn
            )
        self._api = api
        self._snapshot_download = snapshot_download_fn

    def resolve(self, repository: str, revision: str, cache_root: Path) -> ResolvedSource:
        if not repository or "/" not in repository or not revision:
            raise ValueError("Hugging Face repository and revision must be explicit")
        info = self._api.model_info(repository, revision=revision, files_metadata=True)
        expected = 0
        size_known = True
        for sibling in getattr(info, "siblings", ()):
            size = getattr(sibling, "size", None)
            if size is None:
                size_known = False
            else:
                expected += int(size)
        return ResolvedSource(
            provider=self.name,
            repository=repository,
            requested_revision=revision,
            immutable_revision=str(getattr(info, "sha", None) or ""),
            canonical_uri=f"https://huggingface.co/{repository}",
            expected_bytes=expected if size_known else None,
        )

    def fetch(self, source: ResolvedSource, destination: Path, cache_root: Path) -> None:
        try:
            snapshot = Path(
                self._snapshot_download(
                    repo_id=source.repository,
                    repo_type="model",
                    revision=source.immutable_revision,
                    cache_dir=cache_root,
                )
            ).resolve(strict=True)
        except (httpx.NetworkError, httpx.TimeoutException) as error:
            raise TransientSourceError("transient Hugging Face transfer failure") from error
        except httpx.HTTPError as error:
            response = getattr(error, "response", None)
            status = getattr(response, "status_code", None)
            if isinstance(status, int) and (status == 429 or status >= 500):
                raise TransientSourceError(
                    f"transient Hugging Face HTTP failure: {status}"
                ) from error
            raise
        resolved_cache = cache_root.resolve(strict=True)
        try:
            snapshot.relative_to(resolved_cache)
        except ValueError as error:
            raise UnsafePathError("provider snapshot is outside the configured cache") from error
        for item in sorted(snapshot.rglob("*"), key=lambda path: path.as_posix()):
            relative = item.relative_to(snapshot).as_posix()
            validate_upstream_relative_path(relative)
            if item.is_dir():
                continue
            if not item.is_file():
                raise UnsafePathError(f"provider returned a non-file: {relative}")
            try:
                item.resolve(strict=True).relative_to(resolved_cache)
            except ValueError as error:
                message = f"provider file escapes configured cache: {relative}"
                raise UnsafePathError(message) from error
            target = destination.joinpath(*relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, target, follow_symlinks=True)
