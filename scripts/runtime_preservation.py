"""FP-001D metadata contracts. Validation never imports an inference engine."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from scripts.verify_model_zoo import Manifest, ModelEntry, validate_relative_asset_path

Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")]
Version = Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ModelReference(StrictModel):
    entry_id: Identifier
    revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]


class Artifact(StrictModel):
    artifact_id: Identifier
    role: Literal["bootstrap", "wheel", "source", "licence", "input", "procedure", "image"]
    path: Text
    size_bytes: Annotated[int, Field(gt=0)]
    sha256: Digest
    source_uri: Annotated[str, Field(pattern=r"^https://[^\s]+$")]

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        validate_relative_asset_path(value)
        if any(":" in part or part.endswith((".", " ")) for part in value.split("/")):
            raise ValueError("ambiguous Windows path")
        if any(
            re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?", part)
            for part in value.split("/")
        ):
            raise ValueError("Windows device path")
        return value


class Component(StrictModel):
    name: Identifier
    version: Annotated[str, Field(pattern=r"^[0-9][a-zA-Z0-9.+_-]*$")]
    source_uri: Annotated[str, Field(pattern=r"^https://[^\s]+$")]
    artifact_ids: Annotated[list[Identifier], Field(min_length=1)]


class PlatformRequirements(StrictModel):
    operating_system: Text
    os_version: Text
    architecture: Literal["AMD64", "x86_64", "arm64", "aarch64"]
    cpu_requirements: Text
    minimum_ram_bytes: Annotated[int, Field(gt=0)]
    accelerator: Literal["none", "GPU"]
    gpu_requirements: Text
    driver_requirements: Text
    cuda_requirements: Text


class Configuration(StrictModel):
    device: Literal["cpu"]
    dtype: Literal["float32"]
    task: Literal["transcribe"]
    language: Literal["en"]
    sample_rate_hz: Literal[16000]
    max_new_tokens: Annotated[int, Field(ge=1, le=128)]
    local_files_only: Literal[True]
    trust_remote_code: Literal[False]
    threads: Literal[1] = 1
    do_sample: Literal[False] = False


class NativePrerequisite(Component):
    restoration_scope: Literal["existing-host-baseline"]


class ObservedPlatform(StrictModel):
    operating_system: Text
    os_version: Text
    architecture: Literal["AMD64", "x86_64", "arm64", "aarch64"]
    cpu: Text
    total_ram_bytes: Annotated[int, Field(gt=0)]
    available_ram_bytes_before_load: Annotated[int, Field(gt=0)]
    native_versions: dict[Identifier, Text]


class Restoration(StrictModel):
    bootstrap_artifact_id: Identifier
    bootstrap_install_steps: Annotated[list[Text], Field(min_length=1)]
    environment_steps: Annotated[list[Text], Field(min_length=1)]
    start_steps: Annotated[list[Text], Field(min_length=1)]
    offline_only: Literal[True]
    clean_environment_required: Literal[True]


class Acceptance(StrictModel):
    input_artifact_id: Identifier
    network_isolation: Literal["OS-enforced"]
    checks: Literal["restore-load-small-inference"]


class RuntimeDefinition(StrictModel):
    schema_version: Literal["1.0"]
    preservation_id: Identifier
    preservation_version: Version
    model: ModelReference
    runtime: Component
    interpreter: Component
    dependencies: Annotated[list[Component], Field(min_length=1)]
    native_prerequisites: list[NativePrerequisite] = Field(default_factory=list)
    source_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    interpreter_security_note: Text
    artifacts: Annotated[list[Artifact], Field(min_length=1)]
    platform: PlatformRequirements
    configuration: Configuration
    restoration: Restoration
    acceptance: Acceptance
    scope: Literal["offline-restoration-and-inference-only"]

    @model_validator(mode="after")
    def references(self) -> Self:
        artifacts = {item.artifact_id: item for item in self.artifacts}
        roles = {item.role for item in self.artifacts}
        if not {"bootstrap", "wheel", "source", "licence", "input", "procedure"} <= roles:
            raise ValueError("missing durable artifact role (including source/licence/procedure)")
        if len(artifacts) != len(self.artifacts):
            raise ValueError("duplicate artifact id")
        paths = [item.path.casefold() for item in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate artifact path")
        components = [self.runtime, self.interpreter, *self.dependencies]
        names = [component.name for component in components]
        if len(names) != len(set(names)):
            raise ValueError("duplicate component name")
        for component in components:
            if len(component.artifact_ids) != len(set(component.artifact_ids)):
                raise ValueError("duplicate component artifact reference")
            if any(item not in artifacts for item in component.artifact_ids):
                raise ValueError("unknown component artifact")
            expected = "bootstrap" if component is self.interpreter else "wheel"
            if not any(artifacts[item].role == expected for item in component.artifact_ids):
                raise ValueError(
                    f"component requires durable {expected} artifact; image is optional"
                )
        for native in self.native_prerequisites:
            if native.name in names:
                raise ValueError("duplicate native component name")
            names.append(native.name)
            if not native.artifact_ids or any(
                key not in artifacts or artifacts[key].role != "bootstrap"
                for key in native.artifact_ids
            ):
                raise ValueError("native prerequisite requires preserved bootstrap")
        bootstrap = artifacts.get(self.restoration.bootstrap_artifact_id)
        if bootstrap is None or bootstrap.role != "bootstrap":
            raise ValueError("restoration requires bootstrap artifact")
        if bootstrap.artifact_id not in self.interpreter.artifact_ids:
            raise ValueError("bootstrap must belong to interpreter")
        audio = artifacts.get(self.acceptance.input_artifact_id)
        if audio is None or audio.role != "input":
            raise ValueError("acceptance requires preserved input")
        if self.runtime.name != "transformers" or self.interpreter.name != "cpython":
            raise ValueError("FP-001D reference recipe supports CPython/Transformers only")
        if "torch" not in names:
            raise ValueError("reference recipe requires torch dependency")
        if self.platform.accelerator != "none":
            raise ValueError("FP-001D reference recipe is CPU-only")
        return self


class DefinitionReference(StrictModel):
    preservation_id: Identifier
    preservation_version: Version
    sha256: Digest


class EvidenceFile(StrictModel):
    path: Text
    size_bytes: Annotated[int, Field(gt=0)]
    sha256: Digest

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        return Artifact.safe_path(value)


class NetworkEvidence(StrictModel):
    method: Literal["OS-enforced", "not-executed"]
    mechanism: Text
    covers_restoration_and_inference: bool
    external_retrievals: Annotated[int, Field(ge=0)]
    log: EvidenceFile | None
    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None


class ExecutionEvidence(StrictModel):
    account_sid: Text
    controller_sid: Text
    new_account: Literal[True]
    python_location: Text
    environment_location: Text
    system_site_packages: Literal[False]
    bootstrap_exit_code: Literal[0]
    venv_exit_code: Literal[0]
    install_exit_code: Literal[0]
    dependency_check_exit_code: Literal[0]
    inference_exit_code: Literal[0]
    started_at: AwareDatetime
    ended_at: AwareDatetime
    native_restoration_proven: Literal[False]

    @model_validator(mode="after")
    def separate_account(self) -> Self:
        if self.account_sid == self.controller_sid:
            raise ValueError("acceptance requires a new Windows account")
        if self.ended_at < self.started_at:
            raise ValueError("invalid execution timestamps")
        return self


class RuntimeEvidence(StrictModel):
    schema_version: Literal["1.0"]
    run_id: Identifier
    model: ModelReference
    definition: DefinitionReference
    recorded_at: AwareDatetime
    status: Literal["PASSED", "FAILED", "BLOCKED"]
    reason: Text
    restored: bool
    model_loaded: bool
    inference_completed: bool
    clean_environment: bool
    observed_platform: ObservedPlatform | None
    observed_configuration: Configuration | None
    source_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    execution: ExecutionEvidence | None
    execution_log: EvidenceFile | None
    component_versions: dict[Identifier, Text]
    verified_artifacts: dict[Identifier, Digest]
    network: NetworkEvidence
    restoration_log: EvidenceFile | None
    inference_log: EvidenceFile | None
    model_integrity_record: EvidenceFile | None
    input_sha256: Digest | None
    output_sha256: Digest | None
    benchmarked: Literal[False]
    approved_for_runtime: Literal[False]

    @model_validator(mode="after")
    def outcome(self) -> Self:
        if self.inference_completed and not self.model_loaded:
            raise ValueError("inference requires model load")
        if self.model_loaded and not self.restored:
            raise ValueError("load requires restoration")
        if self.status == "PASSED":
            if not all(
                (self.restored, self.model_loaded, self.inference_completed, self.clean_environment)
            ):
                raise ValueError("PASSED requires clean restoration, load and inference")
            if any(
                value is None
                for value in (
                    self.observed_platform,
                    self.restoration_log,
                    self.inference_log,
                    self.model_integrity_record,
                    self.input_sha256,
                    self.output_sha256,
                    self.network.log,
                    self.observed_configuration,
                    self.execution,
                    self.execution_log,
                )
            ):
                raise ValueError("PASSED requires complete evidence")
            if (
                self.network.method != "OS-enforced"
                or not self.network.covers_restoration_and_inference
                or self.network.external_retrievals != 0
            ):
                raise ValueError("PASSED requires offline restoration and inference")
            if self.network.started_at is None or self.network.ended_at is None:
                raise ValueError("PASSED requires network timestamps")
            assert self.execution is not None
            if not (
                self.network.started_at
                <= self.execution.started_at
                <= self.execution.ended_at
                <= self.network.ended_at
            ):
                raise ValueError("network isolation must cover all execution")
        if self.status == "BLOCKED" and any(
            (self.restored, self.model_loaded, self.inference_completed)
        ):
            raise ValueError("BLOCKED cannot claim execution")
        return self


def definition_digest(definition: RuntimeDefinition) -> str:
    """Digest canonical validated JSON, so whitespace/line endings do not alter identity."""
    payload = json.dumps(
        definition.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_link(definition: RuntimeDefinition, manifest: Manifest) -> ModelEntry:
    matches = [model for model in manifest.models if model.entry_id == definition.model.entry_id]
    if len(matches) != 1:
        raise ValueError("model entry_id not found exactly once")
    model = matches[0]
    if model.identity.revision != definition.model.revision:
        raise ValueError("immutable model revision mismatch")
    if model.category != "ASR" or model.format != "safetensors-transformers":
        raise ValueError("reference recipe requires Transformers ASR snapshot")
    if not model.lifecycle.available:
        raise ValueError("model is not catalogued as available")
    return model


def validate_evidence(
    definition: RuntimeDefinition,
    evidence: RuntimeEvidence,
    manifest: Manifest,
) -> None:
    validate_link(definition, manifest)
    if evidence.model != definition.model:
        raise ValueError("evidence model linkage mismatch")
    if (
        evidence.definition.preservation_id != definition.preservation_id
        or evidence.definition.preservation_version != definition.preservation_version
        or evidence.definition.sha256 != definition_digest(definition)
    ):
        raise ValueError("evidence definition linkage mismatch")
    artifacts = {item.artifact_id: item for item in definition.artifacts}
    for key, digest in evidence.verified_artifacts.items():
        if key not in artifacts or artifacts[key].sha256 != digest:
            raise ValueError("evidence artifact digest mismatch")
    if evidence.status != "PASSED":
        return
    if evidence.source_revision != definition.source_revision:
        raise ValueError("source revision mismatch")
    if evidence.observed_configuration != definition.configuration:
        raise ValueError("observed inference configuration mismatch")
    required = {item.artifact_id for item in definition.artifacts if item.role != "image"}
    if not required.issubset(evidence.verified_artifacts):
        raise ValueError("PASSED requires verification of every durable artifact")
    components = [definition.runtime, definition.interpreter, *definition.dependencies]

    def normalized(values: dict[str, str]) -> dict[str, str]:
        result = {re.sub(r"[-_.]+", "-", k).lower(): v for k, v in values.items()}
        if len(result) != len(values):
            raise ValueError("duplicate normalized component name")
        return result

    if normalized(evidence.component_versions) != {item.name: item.version for item in components}:
        raise ValueError("observed component versions differ from definition")
    if evidence.input_sha256 != artifacts[definition.acceptance.input_artifact_id].sha256:
        raise ValueError("acceptance input digest mismatch")
    observed = evidence.observed_platform
    assert observed is not None
    required_platform = definition.platform
    if (
        observed.operating_system != required_platform.operating_system
        or observed.os_version != required_platform.os_version
        or observed.architecture != required_platform.architecture
        or observed.total_ram_bytes < required_platform.minimum_ram_bytes
        or observed.available_ram_bytes_before_load < required_platform.minimum_ram_bytes
        or observed.native_versions != {n.name: n.version for n in definition.native_prerequisites}
    ):
        raise ValueError("observed platform does not satisfy supported profile")


def load_definition(path: Path) -> RuntimeDefinition:
    return RuntimeDefinition.model_validate_json(path.read_text(encoding="utf-8"))
