"""Read-only, offline validation; binary hashing requires an explicit opt-in."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from scripts.runtime_preservation import (
    RuntimeEvidence,
    definition_digest,
    load_definition,
    validate_evidence,
    validate_link,
)
from scripts.verify_model_zoo import load_manifest, resolve_asset_path, sha256_file


def external_root(root: Path, repository: Path) -> Path:
    resolved = root.resolve(strict=True)
    if not resolved.is_dir() or resolved.is_relative_to(repository.resolve()):
        raise ValueError("artifact/evidence root must be a directory outside the Git checkout")
    # Also reject a different Git checkout, including managed worktrees with a .git file.
    if any((parent / ".git").exists() for parent in (resolved, *resolved.parents)):
        raise ValueError("artifact/evidence root must not be inside any Git checkout")
    return resolved


def check_file(root: Path, path: str, size_bytes: int, digest: str, hash_files: bool) -> None:
    candidate = resolve_asset_path(root, path)
    if not candidate.is_file() or candidate.stat().st_size != size_bytes:
        raise ValueError(f"missing file or size mismatch: {path}")
    if hash_files and sha256_file(candidate) != digest:
        raise ValueError(f"SHA-256 mismatch: {path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument(
        "--acceptance",
        action="store_true",
        help="Require passing execution evidence and hash every retained file",
    )
    parser.add_argument(
        "--hash-files",
        action="store_true",
        help="Explicitly hash referenced runtime/evidence files, never model weights",
    )
    args = parser.parse_args(argv)
    try:
        if args.acceptance and not all(
            (args.evidence, args.artifact_root, args.evidence_root, args.hash_files)
        ):
            raise ValueError("--acceptance requires evidence, both roots and --hash-files")
        if args.hash_files and args.artifact_root is None:
            raise ValueError("--hash-files requires --artifact-root")
        definition = load_definition(args.definition)
        manifest = load_manifest(args.manifest)
        validate_link(definition, manifest)
        evidence = None
        if args.evidence:
            evidence = RuntimeEvidence.model_validate_json(
                args.evidence.read_text(encoding="utf-8")
            )
            validate_evidence(definition, evidence, manifest)
        if args.evidence_root and evidence is None:
            raise ValueError("--evidence-root requires --evidence")
        repository = Path(__file__).resolve().parent.parent
        if args.artifact_root:
            root = external_root(args.artifact_root, repository)
            for artifact in definition.artifacts:
                if artifact.role != "image":
                    check_file(
                        root, artifact.path, artifact.size_bytes, artifact.sha256, args.hash_files
                    )
        if args.evidence_root and evidence:
            root = external_root(args.evidence_root, repository)
            records = [
                evidence.restoration_log,
                evidence.inference_log,
                evidence.model_integrity_record,
                evidence.network.log,
                evidence.execution_log,
            ]
            for record in records:
                if record is not None:
                    check_file(root, record.path, record.size_bytes, record.sha256, args.hash_files)
        if args.acceptance:
            assert evidence is not None
            if evidence.status != "PASSED":
                raise ValueError("acceptance requires PASSED execution")
            from scripts.collect_runtime_evidence import collect

            collected = collect(args.artifact_root, args.evidence_root)
            # Timestamp is assigned on collection; all substantive claims must reproduce.
            if collected.model_dump(exclude={"recorded_at"}) != evidence.model_dump(
                exclude={"recorded_at"}
            ):
                raise ValueError("retained logs do not reproduce evidence")
        print(
            json.dumps(
                {
                    "metadata": "VALID",
                    "definition_sha256": definition_digest(definition),
                    "evidence_status": evidence.status if evidence else "NOT_SUPPLIED",
                    "artifact_check": ("SHA256" if args.hash_files else "SIZE_ONLY")
                    if args.artifact_root
                    else "NOT_CHECKED",
                    "evidence_files_checked": bool(args.evidence_root),
                    "runtime_preserved": "EVIDENCE_VERIFIED_HOST_BASELINE_ONLY"
                    if args.acceptance
                    else "NOT_ESTABLISHED_BY_METADATA_VALIDATION",
                },
                sort_keys=True,
            )
        )
        return 0 if evidence is None or evidence.status == "PASSED" else 1
    except (OSError, ValueError) as error:
        print(json.dumps({"metadata": "INVALID", "error": str(error)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
