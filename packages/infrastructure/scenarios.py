"""Bounded offline YAML loading, without tags, aliases, traversal or code evaluation."""

import json
from itertools import islice
from pathlib import Path
from threading import RLock
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError
from yaml.tokens import AliasToken, AnchorToken, TagToken  # type: ignore[import-untyped]

from packages.application.scenarios import (
    ScenarioInvalid,
    ScenarioIssue,
    ScenarioMissing,
    validate_references,
)
from packages.domain.scenario import Scenario
from packages.infrastructure.configuration.settings import UniqueKeyLoader


class ScenarioYamlLoader(UniqueKeyLoader):
    def construct_mapping(self, node: Any, deep: bool = False) -> dict[str, object]:
        result: dict[str, object] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                mark = key_node.start_mark
                raise ScenarioInvalid(
                    ScenarioIssue(
                        f"line:{mark.line + 1}:column:{mark.column + 1}",
                        "duplicate_or_nonstring_key",
                    )
                )
            result[key] = self.construct_object(value_node, deep=deep)
        return result


MAX_BYTES = 1024 * 1024


def load_scenario(content: bytes) -> Scenario:
    if len(content) > MAX_BYTES:
        raise ScenarioInvalid(ScenarioIssue("$", "document_too_large"))
    try:
        text = content.decode("utf-8")
        depth = 0
        for count, token in enumerate(yaml.scan(text)):
            if count > 20000:
                raise ScenarioInvalid(ScenarioIssue("$", "too_many_tokens"))
            if isinstance(token, AliasToken | AnchorToken | TagToken):
                raise ScenarioInvalid(
                    ScenarioIssue(
                        f"line:{token.start_mark.line + 1}:column:{token.start_mark.column + 1}",
                        "forbidden_yaml_construct",
                    )
                )
        for event in yaml.parse(text):
            if isinstance(event, yaml.MappingStartEvent | yaml.SequenceStartEvent):
                depth += 1
                if depth > 32:
                    raise ScenarioInvalid(ScenarioIssue("$", "too_deep"))
            elif isinstance(event, yaml.MappingEndEvent | yaml.SequenceEndEvent):
                depth -= 1
        value = yaml.load(text, Loader=ScenarioYamlLoader)
        scenario = Scenario.model_validate_json(json.dumps(value, allow_nan=False))
    except ScenarioInvalid:
        raise
    except ValidationError as error:
        raise ScenarioInvalid(
            *(
                ScenarioIssue(
                    ".".join(str(part) for part in item["loc"]) or "$",
                    item["type"],
                )
                for item in error.errors(include_input=False, include_context=False)
            )
        ) from None
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        location = f"line:{mark.line + 1}:column:{mark.column + 1}" if mark else "$"
        raise ScenarioInvalid(ScenarioIssue(location, "invalid_yaml")) from None
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ScenarioInvalid(ScenarioIssue("$", "invalid_document")) from None
    validate_references(scenario)
    return scenario


class LocalScenarioCatalogue:
    """One immutable capture. Reconstruct explicitly to load edited versions."""

    def __init__(self, root: Path | None) -> None:
        self._root = root
        self._scenarios: tuple[Scenario, ...] | None = None
        self._lock = RLock()

    def _load(self) -> tuple[Scenario, ...]:
        root = self._root
        if root is None:
            return ()
        if root.is_symlink() or root.is_junction() or not root.is_dir():
            raise ScenarioInvalid(ScenarioIssue("$", "scenario_directory_unavailable"))
        items = []
        identities: set[tuple[str, str]] = set()
        try:
            paths = sorted(islice(root.iterdir(), 513), key=lambda path: path.name)
        except OSError:
            raise ScenarioInvalid(ScenarioIssue("$", "scenario_directory_unavailable")) from None
        if len(paths) > 512:
            raise ScenarioInvalid(ScenarioIssue("$", "too_many_files"))
        for path in paths:
            if path.suffix.lower() not in {".yaml", ".yml"}:
                continue
            if path.is_symlink() or path.is_junction() or not path.is_file():
                raise ScenarioInvalid(ScenarioIssue(path.name, "not_regular_file"))
            try:
                with path.open("rb") as stream:
                    item = load_scenario(stream.read(MAX_BYTES + 1))
            except ScenarioInvalid as error:
                raise ScenarioInvalid(
                    *(
                        ScenarioIssue(f"{path.name}:{issue.location}", issue.code)
                        for issue in error.issues
                    )
                ) from None
            except OSError:
                raise ScenarioInvalid(ScenarioIssue(path.name, "unreadable_file")) from None
            identity = (item.id, item.version)
            if identity in identities:
                raise ScenarioInvalid(ScenarioIssue(path.name, "duplicate_scenario_version"))
            identities.add(identity)
            items.append(item)
        return tuple(sorted(items, key=lambda item: (item.id, item.version)))

    def list(self) -> tuple[Scenario, ...]:
        with self._lock:
            if self._scenarios is None:
                self._scenarios = self._load()
            return self._scenarios

    def get(self, scenario_id: str, version: str | None = None) -> Scenario:
        matches = [
            item
            for item in self.list()
            if item.id == scenario_id and (version is None or item.version == version)
        ]
        if not matches:
            raise ScenarioMissing("Scenario not found")
        if len(matches) != 1:
            raise ScenarioInvalid(ScenarioIssue("version", "version_required"))
        return matches[0]
