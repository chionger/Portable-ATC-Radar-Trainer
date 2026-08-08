from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable
from pathlib import Path

PROHIBITED_DOMAIN_IMPORTS = ("apps", "packages.application", "packages.infrastructure")


def python_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_dir():
            yield from path.rglob("*.py")
        elif path.suffix == ".py":
            yield path


def violations(paths: Iterable[Path]) -> list[str]:
    failures: list[str] = []
    for path in python_files(paths):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            for module in imported:
                prohibited = any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in PROHIBITED_DOMAIN_IMPORTS
                )
                if prohibited:
                    line = getattr(node, "lineno", 0)
                    failures.append(f"{path}:{line}: prohibited domain import '{module}'")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce inward dependency rules.")
    parser.add_argument("paths", nargs="*", type=Path, default=[Path("packages/domain")])
    args = parser.parse_args()
    failures = violations(args.paths)
    if failures:
        print("Architecture boundary violations detected:")
        print("\n".join(failures))
        return 1
    print("Architecture boundaries valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
