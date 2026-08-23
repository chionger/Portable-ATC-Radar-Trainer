from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.model_acquisition import (  # noqa: E402
    AcquisitionError,
    ConfirmationError,
    InsufficientStorageError,
    InterruptedAcquisition,
    StorageReport,
    acquire,
)
from scripts.model_source_huggingface import HuggingFaceSourceProvider  # noqa: E402


def print_storage(report: StorageReport) -> None:
    print(f"expected_bytes={report.expected_bytes}")
    print(f"expected_download_bytes={report.expected_download_bytes}")
    print(f"free_bytes={report.free_bytes}")
    print(f"safety_margin_bytes={report.safety_margin_bytes}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire an explicitly selected model snapshot.")
    parser.add_argument("--provider", choices=["huggingface"], required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--asset-root", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    repository_root = Path(__file__).resolve().parent.parent
    try:
        metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a JSON object")
        result = acquire(
            provider=HuggingFaceSourceProvider(),
            repository=args.repository,
            revision=args.revision,
            asset_root=args.asset_root,
            repository_root=repository_root,
            metadata=metadata,
            assume_yes=args.yes,
            interactive=sys.stdin.isatty(),
            report_storage=print_storage,
        )
    except InsufficientStorageError as error:
        print(f"INSUFFICIENT_STORAGE {error}")
        return 4
    except ConfirmationError as error:
        print(f"CONFIRMATION_REQUIRED {error}")
        return 3
    except InterruptedAcquisition as error:
        print(f"INTERRUPTED {error}")
        return 130
    except (AcquisitionError, OSError, ValueError, json.JSONDecodeError, ValidationError) as error:
        print(f"ACQUISITION_FAILED {error}")
        return 2
    output = {
        "candidate_manifest": str(result.candidate_manifest),
        "expected_bytes": result.storage.expected_bytes,
        "final_directory": str(result.final_directory),
        "free_bytes": result.storage.free_bytes,
        "resolved_revision": result.source.immutable_revision,
        "status": "VERIFIED",
    }
    if args.as_json:
        print(json.dumps(output, sort_keys=True))
    else:
        print("\n".join(f"{key}={value}" for key, value in output.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
