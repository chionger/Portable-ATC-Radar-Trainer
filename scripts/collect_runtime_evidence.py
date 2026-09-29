"""Collect one completed offline run; never execute inference or retrieve artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.runtime_preservation import (
    RuntimeEvidence,
    definition_digest,
    load_definition,
    validate_evidence,
)
from scripts.verify_model_zoo import load_manifest, sha256_file
from scripts.verify_runtime_preservation import check_file, external_root


def validate_observations(network: list[dict[str, Any]], inference: dict[str, Any]) -> None:
    if len(network) < 2:
        raise ValueError("network coverage failed")
    previous = None
    for row in network:
        if (
            not row["isolated"]
            or not row["adapters"]
            or any(a["Status"] == "Up" for a in row["adapters"])
            or any(r["DestinationPrefix"] in {"0.0.0.0/0", "::/0"} for r in row["routes"])
        ):
            raise ValueError("network coverage failed")
        timestamp = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
        if previous is not None and not 0 <= (timestamp - previous).total_seconds() <= 30:
            raise ValueError("network snapshot coverage gap")
        previous = timestamp
    tokens = inference["generated_tokens"]
    if (
        not isinstance(tokens, list)
        or len(tokens) != 1
        or not tokens[0]
        or any(type(token) is not int or token < 0 for token in tokens[0])
        or len(tokens[0]) != inference["generated_token_count"]
    ):
        raise ValueError("missing or inconsistent generated sequence")
    digest = hashlib.sha256(json.dumps(tokens, separators=(",", ":")).encode()).hexdigest()
    if digest != inference["output_sha256"]:
        raise ValueError("generated sequence digest differs")


def collect(bundle: Path, run: Path, *, write_integrity: bool = False) -> RuntimeEvidence:
    repository = Path(__file__).resolve().parents[1]
    external_root(bundle, repository)
    external_root(run, repository)
    definition = load_definition(bundle / "definition.json")
    execution = json.loads((run / "execution.json").read_text(encoding="utf-8-sig"))
    inference = json.loads((run / "inference.json").read_text(encoding="utf-8-sig"))
    network = [
        json.loads(line)
        for line in (run / "network.jsonl").read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    validate_observations(network, inference)
    if inference["definition_sha256"] != definition_digest(definition):
        raise ValueError("executed definition differs")
    verified = {}
    for item in definition.artifacts:
        if item.role != "image":
            check_file(bundle, item.path, item.size_bytes, item.sha256, True)
            verified[item.artifact_id] = item.sha256

    def record(name: str) -> dict[str, object]:
        path = run / name
        return dict(path=name, size_bytes=path.stat().st_size, sha256=sha256_file(path))

    integrity = {
        "checks": inference["model_integrity"],
        "historical_provenance": "source/model-history contains original catalogue, "
        "SHA256.csv and acquisition note; acquisition note has a revision placeholder, "
        "so exact revision linkage relies on catalogue and snapshot path.",
        "limitation": "Large weights were NOT freshly hashed; size check plus historical "
        "catalogue SHA-256/provenance only.",
    }
    integrity_text = json.dumps(integrity, indent=2) + "\n"
    if write_integrity:
        (run / "model-integrity.json").write_text(integrity_text)
    elif (run / "model-integrity.json").read_text() != integrity_text:
        raise ValueError("model integrity record differs from inference log")
    evidence = RuntimeEvidence.model_validate_json(
        json.dumps(
            {
                "schema_version": "1.0",
                "run_id": run.name,
                "model": definition.model.model_dump(),
                "definition": {
                    "preservation_id": definition.preservation_id,
                    "preservation_version": definition.preservation_version,
                    "sha256": definition_digest(definition),
                },
                "recorded_at": datetime.now(UTC),
                "status": "PASSED",
                "reason": "One offline restoration/load/synthetic inference on declared existing "
                "Windows/native baseline. Does not prove clean-OS/bare-machine native restoration.",
                "restored": True,
                "model_loaded": inference["model_loaded"],
                "inference_completed": inference["inference_completed"],
                "clean_environment": True,
                "observed_platform": execution["observed_platform"],
                "observed_configuration": inference["observed_configuration"],
                "source_revision": inference["source_revision"],
                "execution": execution["execution"],
                "execution_log": record("execution.json"),
                "component_versions": {"cpython": inference["python"], **inference["packages"]},
                "verified_artifacts": verified,
                "network": {
                    "method": "OS-enforced",
                    "mechanism": "Operator manually disabled/disconnected "
                    "all network adapters before bootstrap; retained adapter/route snapshots "
                    "throughout. "
                    "Python audit guard and offline flags are defense in depth, not OS isolation.",
                    "covers_restoration_and_inference": True,
                    "external_retrievals": 0,
                    "started_at": network[0]["timestamp"],
                    "ended_at": network[-1]["timestamp"],
                    "log": record("network.jsonl"),
                },
                "restoration_log": record("restoration.txt"),
                "inference_log": record("inference.json"),
                "model_integrity_record": record("model-integrity.json"),
                "input_sha256": inference["input_sha256"],
                "output_sha256": inference["output_sha256"],
                "benchmarked": False,
                "approved_for_runtime": False,
            },
            default=str,
        )
    )
    validate_evidence(
        definition, evidence, load_manifest(bundle / "source/model-zoo/manifest.json")
    )
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    try:
        evidence = collect(args.bundle, args.run, write_integrity=True)
        (args.run / "run.json").write_text(evidence.model_dump_json(indent=2) + "\n")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        (args.run / "collection-failure.json").write_text(
            json.dumps(
                {
                    "status": "FAILED",
                    "error": str(error),
                    "runtime_preserved": False,
                }
            )
            + "\n"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
