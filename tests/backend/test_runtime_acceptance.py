import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.collect_runtime_evidence import validate_observations
from scripts.runtime_preservation import (
    RuntimeDefinition,
    RuntimeEvidence,
    definition_digest,
    validate_evidence,
)
from scripts.verify_model_zoo import Manifest
from scripts.verify_runtime_preservation import main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/runtime-preservation"


def records():
    definition = RuntimeDefinition.model_validate_json((FIXTURES / "definition.json").read_text())
    evidence = RuntimeEvidence.model_validate_json((FIXTURES / "evidence.json").read_text())
    manifest = Manifest.model_validate_json((FIXTURES / "manifest.json").read_text())
    return definition, evidence, manifest


def test_observed_ram_is_capacity_not_requirement_copy():
    definition, evidence, manifest = records()
    data = evidence.model_dump()
    data["observed_platform"]["total_ram_bytes"] *= 2
    validate_evidence(definition, RuntimeEvidence.model_validate(data), manifest)
    data["observed_platform"]["available_ram_bytes_before_load"] = 1
    with pytest.raises(ValueError, match="platform"):
        validate_evidence(definition, RuntimeEvidence.model_validate(data), manifest)


@pytest.mark.parametrize("mutation", ["threads", "source", "tokens"])
def test_execution_bound_to_definition(mutation):
    definition, evidence, manifest = records()
    data = evidence.model_dump()
    if mutation == "source":
        data["source_revision"] = "b" * 40
    else:
        data["observed_configuration"]["max_new_tokens" if mutation == "tokens" else "threads"] = 2
    with pytest.raises(ValueError):
        validate_evidence(definition, RuntimeEvidence.model_validate(data), manifest)


@pytest.mark.parametrize("mutation", ["account", "coverage", "bootstrap", "venv", "check"])
def test_failed_restoration_or_isolation_cannot_pass(mutation):
    _, evidence, _ = records()
    data = evidence.model_dump()
    if mutation == "account":
        data["execution"]["account_sid"] = data["execution"]["controller_sid"]
    elif mutation == "coverage":
        data["network"]["started_at"] = data["network"]["ended_at"]
    else:
        key = {
            "bootstrap": "bootstrap_exit_code",
            "venv": "venv_exit_code",
            "check": "dependency_check_exit_code",
        }[mutation]
        data["execution"][key] = 1
    with pytest.raises(ValueError):
        RuntimeEvidence.model_validate(data)


def test_native_baseline_uses_bootstrap_not_wheel():
    definition, evidence, manifest = records()
    data = definition.model_dump()
    native = copy.deepcopy(data["interpreter"])
    native.update(name="msvc-x64", restoration_scope="existing-host-baseline")
    data["native_prerequisites"] = [native]
    revised = RuntimeDefinition.model_validate(data)
    observed = evidence.model_dump()
    observed["definition"]["sha256"] = definition_digest(revised)
    observed["observed_platform"]["native_versions"] = {"msvc-x64": native["version"]}
    validate_evidence(revised, RuntimeEvidence.model_validate(observed), manifest)
    data["native_prerequisites"][0]["artifact_ids"] = ["torch"]
    with pytest.raises(ValueError, match="native prerequisite"):
        RuntimeDefinition.model_validate(data)


def test_acceptance_requires_both_roots_and_real_hash_checks(capsys):
    assert (
        main(
            [
                "--definition",
                str(FIXTURES / "definition.json"),
                "--manifest",
                str(FIXTURES / "manifest.json"),
                "--acceptance",
            ]
        )
        == 2
    )
    assert "both roots" in capsys.readouterr().out


def test_distribution_names_normalized():
    definition, evidence, manifest = records()
    data = definition.model_dump()
    dependency = copy.deepcopy(data["dependencies"][0])
    dependency["name"] = "typing-extensions"
    data["dependencies"].append(dependency)
    revised = RuntimeDefinition.model_validate(data)
    observed = evidence.model_dump()
    observed["definition"]["sha256"] = definition_digest(revised)
    observed["component_versions"]["typing_extensions"] = dependency["version"]
    validate_evidence(revised, RuntimeEvidence.model_validate(observed), manifest)


def test_schema_json_serializable():
    definition, evidence, _ = records()
    assert json.loads(definition.model_dump_json())["source_revision"] == evidence.source_revision


@pytest.mark.parametrize("mutation", ["up", "route", "gap", "digest", "count"])
def test_retained_observations_reject_false_success(mutation):
    network = [
        {
            "isolated": True,
            "timestamp": f"2026-01-01T00:00:0{i}Z",
            "adapters": [{"Status": "Disabled"}],
            "routes": [],
        }
        for i in range(2)
    ]
    inference = {
        "generated_tokens": [[1, 2]],
        "generated_token_count": 2,
        "output_sha256": hashlib.sha256(b"[[1,2]]").hexdigest(),
    }
    validate_observations(network, inference)
    if mutation == "up":
        network[0]["adapters"][0]["Status"] = "Up"
    elif mutation == "route":
        network[0]["routes"] = [{"DestinationPrefix": "::/0"}]
    elif mutation == "gap":
        network[1]["timestamp"] = "2026-01-01T00:01:00Z"
    elif mutation == "digest":
        inference["output_sha256"] = "0" * 64
    else:
        inference["generated_token_count"] = 3
    with pytest.raises(ValueError):
        validate_observations(network, inference)
