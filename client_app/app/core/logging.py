"""Structured (JSON) logging configuration.

Logs are emitted as single-line JSON to stdout so they can be shipped and
queried by any log aggregator (CloudWatch, Loki, ELK, ...) without parsing
free-form text. This is the baseline for observability at scale.
"""

import json
import logging
from datetime import datetime, timezone
from logging.config import dictConfig

# Attributes that already live on a LogRecord; anything else passed via
# `logger.info(..., extra={...})` is treated as structured context.
_RESERVED = set(
    logging.makeLogRecord({}).__dict__.keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as a single line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Promote any structured context attached via `extra=...`.
        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Route the root logger and uvicorn loggers through the JSON formatter."""
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {"()": f"{__name__}.JsonFormatter"},
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {"handlers": ["default"], "level": level},
            "loggers": {
                name: {"handlers": ["default"], "level": level, "propagate": False}
                for name in ("uvicorn", "uvicorn.access", "uvicorn.error")
            },
        }
    )
