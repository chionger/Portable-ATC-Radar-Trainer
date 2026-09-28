import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_model_assets import violations
from scripts.runtime_preservation import (
    RuntimeDefinition,
    RuntimeEvidence,
    definition_digest,
    validate_evidence,
    validate_link,
)
from scripts.verify_model_zoo import Manifest
from scripts.verify_runtime_preservation import check_file, external_root, main

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/runtime-preservation"


def records():
    definition = RuntimeDefinition.model_validate_json((FIXTURES / "definition.json").read_text())
    evidence = RuntimeEvidence.model_validate_json((FIXTURES / "evidence.json").read_text())
    manifest = Manifest.model_validate_json((FIXTURES / "manifest.json").read_text())
    return definition, evidence, manifest


def test_synthetic_round_trip_and_definition_digest():
    definition, evidence, manifest = records()
    validate_evidence(definition, evidence, manifest)
    assert definition_digest(definition) == evidence.definition.sha256
    assert definition_digest(
        RuntimeDefinition.model_validate_json(definition.model_dump_json(indent=4))
    ) == definition_digest(definition)


@pytest.mark.parametrize(
    "field,value", [("revision", "main"), ("revision", "a" * 39), ("entry_id", "")]
)
def test_invalid_identity(field, value):
    definition, _, _ = records()
    data = definition.model_dump()
    data["model"][field] = value
    with pytest.raises(ValueError):
        RuntimeDefinition.model_validate(data)


@pytest.mark.parametrize(
    "path",
    [
        "../outside",
        "/absolute",
        "C:/temp/file",
        "a\\b",
        "a//b",
        "a/./b",
        "a/file:stream",
        "NUL.txt",
        "a./file",
    ],
)
def test_unsafe_paths(path):
    definition, _, _ = records()
    data = definition.model_dump()
    data["artifacts"][0]["path"] = path
    with pytest.raises(ValueError):
        RuntimeDefinition.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [("sha256", "bad"), ("size_bytes", 0), ("size_bytes", True), ("source_uri", "latest")],
)
def test_invalid_integrity_metadata(field, value):
    definition, _, _ = records()
    data = definition.model_dump()
    data["artifacts"][0][field] = value
    with pytest.raises(ValueError):
        RuntimeDefinition.model_validate(data)


def test_duplicate_paths_and_image_only_rejected():
    definition, _, _ = records()
    data = definition.model_dump()
    data["artifacts"][1]["path"] = data["artifacts"][0]["path"].upper()
    with pytest.raises(ValueError, match="duplicate artifact path"):
        RuntimeDefinition.model_validate(data)
    data = definition.model_dump()
    data["artifacts"][0]["role"] = "image"
    with pytest.raises(ValueError, match="durable"):
        RuntimeDefinition.model_validate(data)


@pytest.mark.parametrize("field,value", [("entry_id", "unknown"), ("revision", "b" * 40)])
def test_exact_manifest_linkage(field, value):
    definition, _, manifest = records()
    data = definition.model_dump()
    data["model"][field] = value
    with pytest.raises(ValueError):
        validate_link(RuntimeDefinition.model_validate(data), manifest)


@pytest.mark.parametrize(
    "field", ["restored", "model_loaded", "inference_completed", "clean_environment"]
)
def test_pass_requires_all_execution_phases(field):
    _, evidence, _ = records()
    data = evidence.model_dump()
    data[field] = False
    with pytest.raises(ValueError):
        RuntimeEvidence.model_validate(data)


@pytest.mark.parametrize(
    "field",
    [
        "restoration_log",
        "inference_log",
        "model_integrity_record",
        "input_sha256",
        "output_sha256",
        "observed_platform",
    ],
)
def test_pass_requires_evidence(field):
    _, evidence, _ = records()
    data = evidence.model_dump()
    data[field] = None
    with pytest.raises(ValueError):
        RuntimeEvidence.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("external_retrievals", 1),
        ("covers_restoration_and_inference", False),
        ("method", "not-executed"),
        ("log", None),
    ],
)
def test_offline_evidence_required(field, value):
    _, evidence, _ = records()
    data = evidence.model_dump()
    data["network"][field] = value
    with pytest.raises(ValueError):
        RuntimeEvidence.model_validate(data)


@pytest.mark.parametrize(
    "mutation", ["model", "definition", "artifacts", "versions", "input", "platform"]
)
def test_cross_record_mismatch(mutation):
    definition, evidence, manifest = records()
    data = evidence.model_dump()
    if mutation == "model":
        data["model"]["revision"] = "b" * 40
    elif mutation == "definition":
        data["definition"]["sha256"] = "0" * 64
    elif mutation == "artifacts":
        data["verified_artifacts"] = {}
    elif mutation == "versions":
        data["component_versions"]["torch"] = "999.0.0"
    elif mutation == "input":
        data["input_sha256"] = "0" * 64
    else:
        data["observed_platform"]["architecture"] = "arm64"
    with pytest.raises(ValueError):
        validate_evidence(definition, RuntimeEvidence.model_validate(data), manifest)


def test_extra_fields_and_runtime_approval_rejected():
    _, evidence, _ = records()
    for key in ("benchmarked", "approved_for_runtime", "runtime_preserved"):
        data = evidence.model_dump()
        data[key] = True
        with pytest.raises(ValueError):
            RuntimeEvidence.model_validate(data)


def test_blocked_evidence_does_not_return_success(tmp_path, capsys):
    _, evidence, _ = records()
    data = evidence.model_dump(mode="json")
    data.update(
        status="BLOCKED",
        reason="Synthetic missing bootstrap",
        restored=False,
        model_loaded=False,
        inference_completed=False,
    )
    path = tmp_path / "blocked.json"
    path.write_text(json.dumps(data))
    assert (
        main(
            [
                "--definition",
                str(FIXTURES / "definition.json"),
                "--manifest",
                str(FIXTURES / "manifest.json"),
                "--evidence",
                str(path),
            ]
        )
        == 1
    )
    assert "NOT_ESTABLISHED_BY_METADATA_VALIDATION" in capsys.readouterr().out


def test_metadata_validation_never_reads_artifacts(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("metadata-only verifier tried to hash assets")

    monkeypatch.setattr("scripts.verify_runtime_preservation.sha256_file", forbidden)
    assert (
        main(
            [
                "--definition",
                str(FIXTURES / "definition.json"),
                "--manifest",
                str(FIXTURES / "manifest.json"),
            ]
        )
        == 0
    )


def test_artifact_size_hash_and_missing(tmp_path):
    import hashlib

    item = tmp_path / "tiny.txt"
    item.write_bytes(b"tiny")
    digest = hashlib.sha256(b"tiny").hexdigest()
    check_file(tmp_path, "tiny.txt", 4, digest, True)
    for name, size, sha in [
        ("missing", 4, digest),
        ("tiny.txt", 5, digest),
        ("tiny.txt", 4, "0" * 64),
    ]:
        with pytest.raises(ValueError):
            check_file(tmp_path, name, size, sha, True)


def test_external_root_rejects_any_git_checkout(tmp_path):
    with pytest.raises(ValueError):
        external_root(ROOT / "model-zoo", ROOT)
    (tmp_path / ".git").write_text("gitdir: somewhere")
    with pytest.raises(ValueError):
        external_root(tmp_path, ROOT)


def test_git_safety_runtime_assets():
    for path in (
        "any/pkg.whl",
        "any/python.exe",
        "model-zoo/a.tar",
        "wheelhouse/a.txt",
        "runtime-assets/a",
        "container-images/sha256",
        "runtime-cache/a",
    ):
        assert violations(ROOT, [path])


def test_schema_files_match_contracts():
    for name, model in (("definition", RuntimeDefinition), ("evidence", RuntimeEvidence)):
        actual = json.loads(
            (ROOT / f"model-zoo/schemas/runtime-preservation-{name}.schema.json").read_text()
        )
        expected = model.model_json_schema()
        expected["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        assert actual == expected


def test_network_audit_blocks_dns_and_socket_in_fresh_process():
    code = """
from scripts.offline_runtime_probe import enable_offline
enable_offline()
import socket
for action in [lambda: socket.getaddrinfo(b'example.com', 443), lambda: socket.socket()]:
    try:
        action()
    except RuntimeError as error:
        assert 'denied network' in str(error)
    else:
        raise AssertionError('network operation was allowed')
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "line",
    [
        "https://example.com/package.whl",
        "-r other.txt",
        "--extra-index-url https://example.com",
        "torch>=2",
        "torch @ https://example.com/torch.whl",
    ],
)
def test_install_rejects_network_lock_before_importing_pip(tmp_path, line):
    lock = tmp_path / "lock.txt"
    lock.write_text(line)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.offline_runtime_probe",
            "install",
            "--wheelhouse",
            str(tmp_path),
            "--lock",
            str(lock),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "only exact package pins" in result.stdout


def test_missing_local_model_fails_without_importing_engine(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.offline_runtime_probe",
            "infer",
            "--model",
            str(tmp_path / "missing"),
            "--audio",
            str(tmp_path / "missing.wav"),
            "--manifest",
            str(ROOT / "model-zoo/manifest.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "existing local snapshot" in result.stdout


def test_no_in_place_manifest_mutation():
    definition, evidence, manifest = records()
    before = copy.deepcopy(manifest.model_dump())
    validate_evidence(definition, evidence, manifest)
    assert before == manifest.model_dump()


def test_missing_wheel_fails_offline_without_cache_or_index(tmp_path):
    lock = tmp_path / "lock.txt"
    lock.write_text("fp001d-nonexistent-synthetic==0.0.1 --hash=sha256:" + "0" * 64)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.offline_runtime_probe",
            "install",
            "--wheelhouse",
            str(tmp_path),
            "--lock",
            str(lock),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert "No matching distribution found" in result.stderr


def test_source_licence_and_restoration_artifacts_are_required():
    definition, _, _ = records()
    for role in ("source", "licence", "procedure"):
        data = definition.model_dump()
        data["artifacts"] = [a for a in data["artifacts"] if a["role"] != role]
        with pytest.raises(ValueError, match="missing durable artifact role"):
            RuntimeDefinition.model_validate(data)
