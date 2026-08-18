from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath

MODEL_WEIGHT_EXTENSIONS = {
    ".ckpt",
    ".gguf",
    ".onnx",
    ".pt",
    ".pth",
    ".safetensors",
    ".tflite",
}
FORBIDDEN_MODEL_DIRECTORIES = {"assets", "cache", "downloads", "staging"}
MODEL_ZOO_ROOT = "model-zoo"
FIXTURE_ROOT = PurePosixPath("tests/fixtures/model-zoo/assets")
MAX_TINY_FIXTURE_BYTES = 4096
MAX_MODEL_ZOO_METADATA_BYTES = 1024 * 1024


def tracked_files(repository_root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=repository_root,
        check=True,
        capture_output=True,
    )
    return sorted(path for path in completed.stdout.decode("utf-8").split("\0") if path)


def violations(repository_root: Path, paths: list[str] | None = None) -> list[str]:
    failures: list[str] = []
    for raw_path in paths if paths is not None else tracked_files(repository_root):
        path = PurePosixPath(raw_path)
        disk_path = repository_root.joinpath(*path.parts)
        is_fixture = path.is_relative_to(FIXTURE_ROOT)
        if is_fixture:
            if disk_path.stat().st_size > MAX_TINY_FIXTURE_BYTES:
                failures.append(
                    f"{raw_path}: model-zoo fixture exceeds {MAX_TINY_FIXTURE_BYTES} bytes"
                )
            continue
        if path.suffix.lower() in MODEL_WEIGHT_EXTENSIONS:
            failures.append(f"{raw_path}: recognized model-weight extension is forbidden")
        if path.parts and path.parts[0] == MODEL_ZOO_ROOT:
            if any(part.lower() in FORBIDDEN_MODEL_DIRECTORIES for part in path.parts[1:-1]):
                failures.append(f"{raw_path}: model asset/staging/cache directory is forbidden")
            if path.suffix.lower() == ".bin":
                failures.append(f"{raw_path}: binary model-zoo asset is forbidden")
            if disk_path.exists() and disk_path.stat().st_size > MAX_MODEL_ZOO_METADATA_BYTES:
                failures.append(
                    f"{raw_path}: suspiciously large file is forbidden in model-zoo metadata"
                )
    return sorted(set(failures))


def main() -> int:
    repository_root = Path(__file__).resolve().parent.parent
    failures = violations(repository_root)
    if failures:
        print("Tracked model-asset safety violations detected:")
        print("\n".join(failures))
        return 1
    print("Tracked model-asset safety valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
