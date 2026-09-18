"""Allowlisted JSON records with bounded local rotation; no raw application text."""

import json
import logging
from datetime import UTC, datetime
from enum import StrEnum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import UUID

from packages.domain.health import MetricObservation


class LogEvent(StrEnum):
    REQUEST_COMPLETED = "request.completed"
    REQUEST_FAILED = "request.failed"
    COMPONENT_CHANGED = "component.health_changed"


class LocalFileHandler(RotatingFileHandler):
    def handleError(self, record: logging.LogRecord) -> None:
        # Do not let logging print a traceback containing a private file path.
        raise OSError("structured logging unavailable") from None


class StructuredLog:
    def __init__(
        self,
        *,
        level: str = "INFO",
        path: Path | None = None,
        max_bytes: int = 1_000_000,
        backup_count: int = 3,
    ) -> None:
        self.logger = logging.Logger("atc.structured", level=level)
        handler: logging.Handler
        if path is None:
            handler = logging.StreamHandler()
        else:
            # Configuration already validates a local absolute path. Direct users
            # must also supply one; no implicit parent directory creation.
            from packages.infrastructure.configuration.settings import absolute_local_path

            absolute_local_path(str(path))
            handler = LocalFileHandler(
                path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8", delay=True
            )
        handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(handler)

    def emit(
        self,
        event: LogEvent,
        *,
        correlation_id: UUID,
        status_code: int | None = None,
        metric: MetricObservation | None = None,
        **private_fields: object,
    ) -> None:
        # Deliberately discard unknown fields, not just a blacklist of secret names.
        if not isinstance(event, LogEvent) or not isinstance(correlation_id, UUID):
            raise ValueError("log event and correlation identifier must be typed")
        record: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event.value,
            "correlation_id": str(correlation_id),
        }
        if status_code is not None:
            if type(status_code) is not int or not 100 <= status_code <= 599:
                raise ValueError("invalid HTTP status")
            record["status_code"] = status_code
        if metric is not None:
            record["metric"] = MetricObservation.model_validate_json(
                metric.model_dump_json()
            ).model_dump(mode="json")
        level = logging.ERROR if event == LogEvent.REQUEST_FAILED else logging.INFO
        self.logger.log(
            level, json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
        )

    def close(self) -> None:
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
