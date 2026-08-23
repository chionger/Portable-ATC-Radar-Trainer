from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from scripts.model_acquisition import TransientSourceError, UnsafePathError
from scripts.model_source_huggingface import HuggingFaceSourceProvider

SHA = "b" * 40


class FakeApi:
    def __init__(self) -> None:
        self.arguments: tuple[str, str, bool] | None = None

    def model_info(self, repository: str, revision: str, files_metadata: bool):
        self.arguments = (repository, revision, files_metadata)
        return SimpleNamespace(
            sha=SHA,
            siblings=[SimpleNamespace(size=4), SimpleNamespace(size=6)],
        )


def test_hugging_face_resolves_requested_revision_to_full_sha(tmp_path: Path) -> None:
    api = FakeApi()
    provider = HuggingFaceSourceProvider(api=api, snapshot_download_fn=lambda **_: "unused")

    source = provider.resolve("owner/model", "release-tag", tmp_path)

    assert api.arguments == ("owner/model", "release-tag", True)
    assert source.requested_revision == "release-tag"
    assert source.immutable_revision == SHA
    assert source.expected_bytes == 10


def test_hugging_face_download_uses_resolved_sha_and_external_cache(tmp_path: Path) -> None:
    cache = tmp_path / "external-cache"
    snapshot = cache / "models--owner--model" / "snapshots" / SHA
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_download(**kwargs: object) -> str:
        calls.append(kwargs)
        return str(snapshot)

    provider = HuggingFaceSourceProvider(api=FakeApi(), snapshot_download_fn=fake_download)
    source = provider.resolve("owner/model", "main", tmp_path / "cache")
    destination = tmp_path / "destination"
    destination.mkdir()
    provider.fetch(source, destination, cache)

    assert calls == [
        {
            "repo_id": "owner/model",
            "repo_type": "model",
            "revision": SHA,
            "cache_dir": cache,
        }
    ]
    assert (destination / "config.json").read_text(encoding="utf-8") == "{}"


def test_hugging_face_rejects_snapshot_outside_configured_cache(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    provider = HuggingFaceSourceProvider(
        api=FakeApi(), snapshot_download_fn=lambda **_: str(outside)
    )
    source = provider.resolve("owner/model", "main", tmp_path / "cache")
    cache = tmp_path / "cache"
    cache.mkdir()
    destination = tmp_path / "destination"
    destination.mkdir()

    with pytest.raises(UnsafePathError, match="outside"):
        provider.fetch(source, destination, cache)


def test_hugging_face_maps_network_timeouts_to_retryable_failure(tmp_path: Path) -> None:
    def timed_out(**_: object) -> str:
        raise httpx.ReadTimeout("timed out")

    provider = HuggingFaceSourceProvider(api=FakeApi(), snapshot_download_fn=timed_out)
    source = provider.resolve("owner/model", "main", tmp_path / "cache")

    with pytest.raises(TransientSourceError, match="transient"):
        provider.fetch(source, tmp_path / "destination", tmp_path / "cache")
