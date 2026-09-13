from __future__ import annotations

from typing import Annotated, Literal, Protocol

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

SEMVER_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
RUN_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]*$"
DEFINITION_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]*$"


class IdentityLike(Protocol):
    revision: str


class ModelEntryLike(Protocol):
    entry_id: str
    category: str
    identity: IdentityLike


class ManifestLike(Protocol):
    models: list[ModelEntryLike]


BENCHMARK_CATEGORY_TO_MODEL_CATEGORY = {
    "ASR": "ASR",
    "LLM": "LLM",
    "TTS": "TTS",
    "VISION": "VISION",
    "EMBEDDING": "OTHER_LOCAL_AI",
    "RERANKING": "OTHER_LOCAL_AI",
    "SAFETY": "OTHER_LOCAL_AI",
    "MULTIMODAL": "OTHER_LOCAL_AI",
    "OTHER_LOCAL_AI": "OTHER_LOCAL_AI",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class BenchmarkRef(StrictModel):
    benchmark_id: Annotated[str, Field(min_length=1)]
    benchmark_version: Annotated[str, Field(min_length=1, pattern=SEMVER_PATTERN)]


class ModelRef(StrictModel):
    entry_id: Annotated[str, Field(min_length=1)]
    revision: Annotated[str, Field(min_length=1)]


class EvaluationSet(StrictModel):
    id: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    description: Annotated[str, Field(min_length=1)]


class Metric(StrictModel):
    metric_id: Annotated[str, Field(min_length=1, pattern=DEFINITION_ID_PATTERN)]
    description: Annotated[str, Field(min_length=1)]
    unit: Annotated[str, Field(min_length=1)]
    direction: Literal["higher_is_better", "lower_is_better", "informational"]


class AcceptanceCriterion(StrictModel):
    metric_id: Annotated[str, Field(min_length=1)]
    operator: Literal["lt", "lte", "gt", "gte", "eq"]
    threshold: Annotated[float, Field(allow_inf_nan=False)]


class BenchmarkDefinition(StrictModel):
    schema_version: Literal["1.0"]
    benchmark_id: Annotated[str, Field(min_length=1, pattern=DEFINITION_ID_PATTERN)]
    benchmark_version: Annotated[str, Field(min_length=1, pattern=SEMVER_PATTERN)]
    name: Annotated[str, Field(min_length=1)]
    category: Literal[
        "ASR",
        "LLM",
        "TTS",
        "VISION",
        "EMBEDDING",
        "RERANKING",
        "SAFETY",
        "MULTIMODAL",
        "OTHER_LOCAL_AI",
    ]
    purpose: Annotated[str, Field(min_length=1)]
    evaluation_set: EvaluationSet
    metrics: Annotated[list[Metric], Field(min_length=1)]
    acceptance_criteria: list[AcceptanceCriterion]

    @model_validator(mode="after")
    def validate_metric_ids(self):
        ids = [metric.metric_id for metric in self.metrics]
        if len(ids) != len(set(ids)):
            raise ValueError("metric ids must be unique")
        for criterion in self.acceptance_criteria:
            if criterion.metric_id not in ids:
                raise ValueError("acceptance criterion references undefined metric")
        return self


class Accelerator(StrictModel):
    type: Literal["GPU", "NPU", "OTHER"]
    name: Annotated[str, Field(min_length=1)]
    memory_bytes: Annotated[int, Field(ge=0)]


class Hardware(StrictModel):
    profile_id: Annotated[str, Field(min_length=1)]
    cpu: Annotated[str, Field(min_length=1)]
    ram_bytes: Annotated[int, Field(ge=0)]
    accelerators: list[Accelerator]


class Runtime(StrictModel):
    name: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(min_length=1)]
    operating_system: Annotated[str, Field(min_length=1)]
    configuration: dict[str, object]


class Measurement(StrictModel):
    metric_id: Annotated[str, Field(min_length=1)]
    value: Annotated[float, Field(allow_inf_nan=False)]


class Outcome(StrictModel):
    status: Literal["COMPLETED", "FAILED", "INVALID"]
    criteria_met: bool | None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_criteria_met(self):
        if self.status != "COMPLETED" and self.criteria_met is not None:
            raise ValueError("non-completed outcome requires criteria_met to be null")
        return self


class Evidence(StrictModel):
    type: Literal["LOG", "RAW_RESULT", "SUMMARY", "OTHER"]
    path: Annotated[str, Field(min_length=1)]
    sha256: Annotated[str, Field(pattern=SHA256_PATTERN)] | None = None


class BenchmarkResult(StrictModel):
    schema_version: Literal["1.0"]
    run_id: Annotated[str, Field(min_length=1, pattern=RUN_ID_PATTERN)]
    benchmark: BenchmarkRef
    model: ModelRef
    executed_at: AwareDatetime
    hardware: Hardware
    runtime: Runtime
    measurements: Annotated[list[Measurement], Field(min_length=1)]
    outcome: Outcome
    evidence: list[Evidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_measurement_ids(self):
        ids = [measurement.metric_id for measurement in self.measurements]
        if len(ids) != len(set(ids)):
            raise ValueError("measurement metric ids must be unique")
        return self


def validate_benchmark_reference(definition: BenchmarkDefinition, result: BenchmarkResult) -> None:
    if result.benchmark.benchmark_id != definition.benchmark_id:
        raise ValueError("benchmark id does not match definition")
    if result.benchmark.benchmark_version != definition.benchmark_version:
        raise ValueError("benchmark version does not match definition")
    defined_metrics = {metric.metric_id for metric in definition.metrics}
    for measurement in result.measurements:
        if measurement.metric_id not in defined_metrics:
            raise ValueError("result references undefined metric")
    if result.outcome.status == "COMPLETED":
        measured_metrics = {measurement.metric_id for measurement in result.measurements}
        if measured_metrics != defined_metrics:
            raise ValueError("completed result must contain exactly the defined metrics")


def validate_model_reference(result: BenchmarkResult, model_entry: ModelEntryLike) -> None:
    if result.model.entry_id != model_entry.entry_id:
        raise ValueError("model entry id does not match manifest")
    if result.model.revision != model_entry.identity.revision:
        raise ValueError("model revision does not match manifest")


def validate_manifest_model_reference(
    result: BenchmarkResult, manifest: ManifestLike
) -> ModelEntryLike:
    for model_entry in manifest.models:
        if model_entry.entry_id == result.model.entry_id:
            validate_model_reference(result, model_entry)
            return model_entry
    raise ValueError("model entry id not found in manifest")


def validate_category_compatibility(
    definition: BenchmarkDefinition, model_entry: ModelEntryLike
) -> None:
    expected_category = BENCHMARK_CATEGORY_TO_MODEL_CATEGORY[definition.category]
    if model_entry.category != expected_category:
        raise ValueError("benchmark category is not compatible with model category")


def evaluate_criterion(value: float, criterion: AcceptanceCriterion) -> bool:
    if criterion.operator == "lt":
        return value < criterion.threshold
    if criterion.operator == "lte":
        return value <= criterion.threshold
    if criterion.operator == "gt":
        return value > criterion.threshold
    if criterion.operator == "gte":
        return value >= criterion.threshold
    if criterion.operator == "eq":
        return value == criterion.threshold
    raise ValueError("unsupported acceptance criterion operator")


def validate_criteria_outcome(definition: BenchmarkDefinition, result: BenchmarkResult) -> None:
    if result.outcome.status != "COMPLETED":
        return
    if not definition.acceptance_criteria:
        if result.outcome.criteria_met is not None:
            raise ValueError("criteria_met must be null when no acceptance criteria are defined")
        return
    values = {measurement.metric_id: measurement.value for measurement in result.measurements}
    calculated = all(
        evaluate_criterion(values[criterion.metric_id], criterion)
        for criterion in definition.acceptance_criteria
    )
    if result.outcome.criteria_met != calculated:
        raise ValueError("criteria_met does not match benchmark measurements")


def validate_benchmark_evidence(
    definition: BenchmarkDefinition,
    result: BenchmarkResult,
    manifest: ManifestLike,
) -> ModelEntryLike:
    validate_benchmark_reference(definition, result)
    model_entry = validate_manifest_model_reference(result, manifest)
    validate_category_compatibility(definition, model_entry)
    validate_criteria_outcome(definition, result)
    return model_entry
