"""Launch the API with validated settings, or print a redacted local report."""

import argparse
import json
import logging
from collections.abc import Sequence
from pathlib import Path

import uvicorn

from packages.infrastructure.configuration import ConfigurationError, load_settings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--show-config", action="store_true")
    parser.add_argument("--dev-web", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    api: dict[str, object] = {}
    if args.host is not None:
        api["host"] = args.host
    if args.port is not None:
        api["port"] = args.port
    try:
        settings = load_settings(args.config, overrides={"api": api})
    except ConfigurationError as error:
        print(str(error))
        return 2
    if args.show_config:
        print(json.dumps(settings.redacted_report(), indent=2, sort_keys=True))
        return 0
    if args.dev_web:
        host: str = settings.api.host
        host = f"[{host}]" if ":" in host else host
        print(f"http://{host}:{settings.api.port}")
        return 0
    logging.basicConfig(level=settings.logging.level)
    # Import after validation; the injected settings include CLI overrides.
    from apps.api.factory import create_app

    uvicorn.run(
        create_app(settings),
        host=settings.api.host,
        port=settings.api.port,
        log_level=settings.logging.level.lower(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
