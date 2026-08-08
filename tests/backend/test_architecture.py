from pathlib import Path

from scripts.check_architecture import violations


def test_domain_layer_has_valid_dependencies() -> None:
    assert violations([Path("packages/domain")]) == []


def test_invalid_domain_dependency_fixture_is_detected() -> None:
    failures = violations([Path("tests/fixtures/invalid_domain_dependency.py")])

    assert len(failures) == 1
    assert "prohibited domain import 'packages.infrastructure'" in failures[0]

