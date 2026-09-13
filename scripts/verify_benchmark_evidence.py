import argparse
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from scripts.benchmark_evidence import (
    BenchmarkDefinition,
    BenchmarkResult,
    validate_benchmark_evidence,
)
from scripts.verify_model_zoo import Manifest


def load_json(path: Path, model_type):
    return model_type.model_validate_json(path.read_text(encoding="utf-8"))


def verify_benchmark_evidence(definition_path: Path, result_path: Path, manifest_path: Path):
    definition = load_json(definition_path, BenchmarkDefinition)
    result = load_json(result_path, BenchmarkResult)
    manifest = load_json(manifest_path, Manifest)
    return validate_benchmark_evidence(definition, result, manifest)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate benchmark evidence against its definition and model manifest."
    )
    parser.add_argument("--definition", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        model_entry = verify_benchmark_evidence(args.definition, args.result, args.manifest)
    except (OSError, ValidationError, ValueError) as error:
        print(f"INVALID_BENCHMARK_EVIDENCE {error}")
        return 2
    print(f"VALID_BENCHMARK_EVIDENCE entry={model_entry.entry_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
