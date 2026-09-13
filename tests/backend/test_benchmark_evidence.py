from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.benchmark_evidence import (
    BenchmarkDefinition,
    BenchmarkResult,
    validate_benchmark_evidence,
)
from scripts.verify_benchmark_evidence import main
from scripts.verify_model_zoo import Manifest

ROOT = Path(__file__).resolve().parents[2]
DEFINITION_PATH = (
    ROOT / "tests" / "fixtures" / "benchmark-evidence" / "synthetic-latency-1.0.0.json"
)
RESULT_PATH = (
    ROOT / "tests" / "fixtures" / "benchmark-evidence" / "synthetic-asr-latency-run-001.json"
)
MANIFEST_PATH = ROOT / "tests" / "fixtures" / "model-zoo" / "manifest.json"


def test_valid_benchmark_evidence():
    definition = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    )
    result = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8"))
    manifest = Manifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    model_entry = validate_benchmark_evidence(definition, result, manifest)
    assert model_entry.entry_id == "synthetic-asr-verified"
    assert model_entry.identity.revision == "test-revision-001"


def test_rejects_model_revision_mismatch():
    definition = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    )
    result = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8"))
    manifest = Manifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    result = result.model_copy(
        update={"model": result.model.model_copy(update={"revision": "wrong-revision"})}
    )
    with pytest.raises(ValueError, match="model revision does not match manifest"):
        validate_benchmark_evidence(definition, result, manifest)


def test_rejects_unknown_model():
    definition = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    )
    result = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8"))
    manifest = Manifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    result = result.model_copy(
        update={"model": result.model.model_copy(update={"entry_id": "unknown-model"})}
    )
    with pytest.raises(ValueError, match="model entry id not found in manifest"):
        validate_benchmark_evidence(definition, result, manifest)


def test_rejects_benchmark_version_mismatch():
    definition = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    )
    result = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8"))
    manifest = Manifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    result = result.model_copy(
        update={"benchmark": result.benchmark.model_copy(update={"benchmark_version": "9.9.9"})}
    )
    with pytest.raises(ValueError, match="benchmark version does not match definition"):
        validate_benchmark_evidence(definition, result, manifest)


def test_rejects_undefined_result_metric():
    definition = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    )
    result = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8"))
    manifest = Manifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    result.measurements[0].metric_id = "unknown-metric"
    with pytest.raises(ValueError, match="result references undefined metric"):
        validate_benchmark_evidence(definition, result, manifest)


def test_rejects_missing_completed_metric():
    definition = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    )
    result = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8"))
    manifest = Manifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    result.measurements = []
    with pytest.raises(
        ValueError, match="completed result must contain exactly the defined metrics"
    ):
        validate_benchmark_evidence(definition, result, manifest)


def test_accepts_valid_failing_benchmark():
    definition = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    )
    result = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8"))
    manifest = Manifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    result.measurements[0].value = 142
    result.outcome.criteria_met = False
    model_entry = validate_benchmark_evidence(definition, result, manifest)
    assert model_entry.entry_id == "synthetic-asr-verified"


def test_rejects_incorrect_criteria_outcome():
    definition = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    )
    result = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8"))
    manifest = Manifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    result.measurements[0].value = 142
    result.outcome.criteria_met = True
    with pytest.raises(ValueError, match="criteria_met does not match benchmark measurements"):
        validate_benchmark_evidence(definition, result, manifest)


def test_accepts_informational_benchmark_without_criteria():
    definition = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    )
    result = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8"))
    manifest = Manifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    definition.acceptance_criteria = []
    result.outcome.criteria_met = None
    model_entry = validate_benchmark_evidence(definition, result, manifest)
    assert model_entry.entry_id == "synthetic-asr-verified"


def test_rejects_criteria_outcome_for_informational_benchmark():
    definition = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    )
    result = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8"))
    manifest = Manifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    definition.acceptance_criteria = []
    result.outcome.criteria_met = True
    with pytest.raises(
        ValueError, match="criteria_met must be null when no acceptance criteria are defined"
    ):
        validate_benchmark_evidence(definition, result, manifest)


def test_rejects_benchmark_category_mismatch():
    definition = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    )
    result = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8"))
    manifest = Manifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    definition.category = "LLM"
    with pytest.raises(
        ValueError, match="benchmark category is not compatible with model category"
    ):
        validate_benchmark_evidence(definition, result, manifest)


def test_rejects_duplicate_definition_metrics():
    data = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    ).model_dump()
    data["metrics"].append(dict(data["metrics"][0]))
    with pytest.raises(ValidationError, match="metric ids must be unique"):
        BenchmarkDefinition.model_validate(data)


def test_rejects_duplicate_result_measurements():
    data = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8")).model_dump()
    data["measurements"].append(dict(data["measurements"][0]))
    with pytest.raises(ValidationError, match="measurement metric ids must be unique"):
        BenchmarkResult.model_validate(data)


def test_rejects_criterion_for_undefined_metric():
    data = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    ).model_dump()
    data["acceptance_criteria"][0]["metric_id"] = "undefined-metric"
    with pytest.raises(ValidationError, match="acceptance criterion references undefined metric"):
        BenchmarkDefinition.model_validate(data)


def test_rejects_failed_result_with_criteria_value():
    data = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8")).model_dump()
    data["outcome"]["status"] = "FAILED"
    data["outcome"]["criteria_met"] = True
    with pytest.raises(
        ValidationError, match="non-completed outcome requires criteria_met to be null"
    ):
        BenchmarkResult.model_validate(data)


def test_accepts_failed_result_without_criteria_value():
    definition = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    )
    result = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8"))
    manifest = Manifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    result.outcome.status = "FAILED"
    result.outcome.criteria_met = None
    model_entry = validate_benchmark_evidence(definition, result, manifest)
    assert model_entry.entry_id == "synthetic-asr-verified"


def test_rejects_unknown_result_field():
    data = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8")).model_dump()
    data["unexpected_field"] = "not-allowed"
    with pytest.raises(ValidationError):
        BenchmarkResult.model_validate(data)


def test_cli_accepts_valid_benchmark_evidence():
    exit_code = main(
        [
            "--definition",
            str(DEFINITION_PATH),
            "--result",
            str(RESULT_PATH),
            "--manifest",
            str(MANIFEST_PATH),
        ]
    )
    assert exit_code == 0


def test_cli_rejects_invalid_benchmark_evidence():
    exit_code = main(
        [
            "--definition",
            str(DEFINITION_PATH),
            "--result",
            str(RESULT_PATH),
            "--manifest",
            str(ROOT / "model-zoo" / "manifest.json"),
        ]
    )
    assert exit_code == 2


def test_rejects_invalid_run_id():
    data = BenchmarkResult.model_validate_json(RESULT_PATH.read_text(encoding="utf-8")).model_dump()
    data["run_id"] = "INVALID RUN ID"
    with pytest.raises(ValidationError):
        BenchmarkResult.model_validate(data)


def test_rejects_invalid_definition_identifiers_and_version():
    data = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    ).model_dump()

    invalid_id = dict(data)
    invalid_id["benchmark_id"] = "INVALID BENCHMARK ID"
    with pytest.raises(ValidationError):
        BenchmarkDefinition.model_validate(invalid_id)

    invalid_version = dict(data)
    invalid_version["benchmark_version"] = "1.0"
    with pytest.raises(ValidationError):
        BenchmarkDefinition.model_validate(invalid_version)


def test_rejects_empty_required_metric_lists():
    definition = BenchmarkDefinition.model_validate_json(
        DEFINITION_PATH.read_text(encoding="utf-8")
    ).model_dump()
    definition["metrics"] = []
    with pytest.raises(ValidationError):
        BenchmarkDefinition.model_validate(definition)

    result = BenchmarkResult.model_validate_json(
        RESULT_PATH.read_text(encoding="utf-8")
    ).model_dump()
    result["measurements"] = []
    with pytest.raises(ValidationError):
        BenchmarkResult.model_validate(result)


def test_rejects_invalid_hash_and_negative_memory():
    result = BenchmarkResult.model_validate_json(
        RESULT_PATH.read_text(encoding="utf-8")
    ).model_dump()

    result["evidence"] = [{"type": "LOG", "path": "synthetic.log", "sha256": "ABC123"}]
    with pytest.raises(ValidationError):
        BenchmarkResult.model_validate(result)

    result = BenchmarkResult.model_validate_json(
        RESULT_PATH.read_text(encoding="utf-8")
    ).model_dump()
    result["hardware"]["ram_bytes"] = -1
    with pytest.raises(ValidationError):
        BenchmarkResult.model_validate(result)

    result = BenchmarkResult.model_validate_json(
        RESULT_PATH.read_text(encoding="utf-8")
    ).model_dump()
    result["hardware"]["accelerators"] = [
        {"type": "GPU", "name": "synthetic-gpu", "memory_bytes": -1}
    ]
    with pytest.raises(ValidationError):
        BenchmarkResult.model_validate(result)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_rejects_nonfinite_measurements_and_thresholds(value):
    definition = BenchmarkDefinition.model_validate_json(DEFINITION_PATH.read_text()).model_dump()
    definition["acceptance_criteria"][0]["threshold"] = value
    with pytest.raises(ValidationError, match="finite number"):
        BenchmarkDefinition.model_validate(definition)
    result = BenchmarkResult.model_validate_json(RESULT_PATH.read_text()).model_dump()
    result["measurements"][0]["value"] = value
    with pytest.raises(ValidationError, match="finite number"):
        BenchmarkResult.model_validate(result)


def test_rejects_execution_time_without_timezone():
    text = RESULT_PATH.read_text().replace("2026-09-06T12:00:00Z", "2026-09-06T12:00:00")
    with pytest.raises(ValidationError, match="timezone"):
        BenchmarkResult.model_validate_json(text)
