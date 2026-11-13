"""Structured logging configuration and redaction processors.

Governed by:
- SDD 005 / M1-D08: one structured format for API and worker processes.
- INV-016: secrets, credentials, and sensitive payloads never reach logs.

Configuration is process-global and must be called once per process before
emitting events. Both entrypoints (API and worker) call `configure_logging`
with the same processor chain; only the `service` attribute differs.
"""

import logging
import sys
from collections.abc import Callable, MutableMapping
from typing import Any

import structlog

from app.core.config import Settings, get_settings
from app.core.correlation import current_correlation_id
from app.core.logging.filters import redact_sensitive_data

EventDict = MutableMapping[str, Any]
Processor = Callable[[Any, str, EventDict], EventDict]


def _add_service_name(service: str) -> Processor:
    """Return a processor stamping the emitting process role."""

    def processor(_logger: Any, _method_name: str, event_dict: EventDict) -> EventDict:
        event_dict.setdefault("service", service)
        return event_dict

    return processor


def add_correlation_id(_logger: Any, _method_name: str, event_dict: EventDict) -> EventDict:
    """Attach the active correlation identifier, when one is bound."""
    correlation_id = current_correlation_id()
    if correlation_id is not None:
        event_dict.setdefault("correlation_id", correlation_id)
    return event_dict


def _build_processors(service: str) -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        add_correlation_id,
        _add_service_name(service),
        redact_sensitive_data,
    ]


def configure_logging(
    settings: Settings | None = None,
    *,
    service: str = "api",
) -> None:
    """Configure structured JSON logging for the current process.

    Local development uses `ConsoleRenderer` for readability; every other
    environment emits one JSON object per line. Standard-library loggers
    (uvicorn, SQLAlchemy) pass through the same processors and renderer so all
    process output is consistent and redacted.
    """
    resolved = settings or get_settings()
    level = getattr(logging, resolved.log_level, logging.INFO)
    shared_processors = _build_processors(service)

    if resolved.environment == "local":
        renderer: Any = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def get_logger(name: str | None = None) -> Any:
    """Return a structlog logger for application modules."""
    return structlog.get_logger(name)


__all__ = ["add_correlation_id", "configure_logging", "get_logger"]
