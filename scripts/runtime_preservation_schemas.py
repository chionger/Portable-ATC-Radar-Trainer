"""Generate/check structural schemas; cross-record rules remain in the verifier."""

import argparse
import json
from pathlib import Path

from scripts.runtime_preservation import RuntimeDefinition, RuntimeEvidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "model-zoo" / "schemas"
    for name, model in (("definition", RuntimeDefinition), ("evidence", RuntimeEvidence)):
        path = root / f"runtime-preservation-{name}.schema.json"
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        content = json.dumps(schema, indent=2, sort_keys=True) + "\n"
        if args.check:
            if path.read_text(encoding="utf-8") != content:
                print(f"Schema drift: {path.name}")
                return 1
        else:
            path.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
