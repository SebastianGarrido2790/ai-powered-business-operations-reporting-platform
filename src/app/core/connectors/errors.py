"""Connector exception hierarchy and error classification.

Governed by:
- INV-013: secrets must remain outside source code, logs, and error messages.
- ADR-002: clear security boundaries and credential protection.
- M2-D01: classified connector errors for workflow and retry decisions.
"""

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from app.core.connectors.contract import ConnectorType

# Pattern to redact credentials in URIs (e.g., postgresql://user:pass@host:5432/db)
_URI_CREDENTIAL_PATTERN = re.compile(r"://([^:]+):([^@]+)@")
# Patterns for common secret key-value pairs
_KV_SECRET_PATTERN = re.compile(
    r"(?i)\b(password|secret|token|api[_-]?key|access[_-]?token|auth)\s*[:=]\s*['\"]?([^'\"\s,;]+)['\"]?"
)


def sanitize_text(text: str) -> str:
    """Scrub sensitive information such as passwords, tokens, and DSN credentials."""
    if not text:
        return text
    # Redact URI credentials: postgresql://user:***@host
    redacted = _URI_CREDENTIAL_PATTERN.sub(r"://\1:***@", text)
    # Redact key-value secrets: password=***
    redacted = _KV_SECRET_PATTERN.sub(r"\1=***", redacted)
    return redacted


class ConnectorErrorClass(StrEnum):
    """Classification of connector errors for recovery and failure handling."""

    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    TRANSIENT = "transient"
    PERMANENT = "permanent"


class ConnectorError(Exception):
    """Base class for all connector failures."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        source_id: str | None = None,
        connector_type: ConnectorType | str | None = None,
        error_class: ConnectorErrorClass = ConnectorErrorClass.PERMANENT,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        sanitized_msg = sanitize_text(message)
        super().__init__(sanitized_msg)
        self.raw_message = sanitized_msg
        self.code = code
        self.source_id = source_id
        if isinstance(connector_type, str) and not isinstance(connector_type, ConnectorType):
            try:
                self.connector_type: ConnectorType | None = ConnectorType(connector_type)
            except ValueError:
                self.connector_type = None
        else:
            self.connector_type = connector_type
        self.error_class = error_class

        if details:
            sanitized_details: dict[str, Any] = {}
            for k, v in details.items():
                if isinstance(v, str):
                    sanitized_details[k] = sanitize_text(v)
                else:
                    sanitized_details[k] = v
            self.details: Mapping[str, Any] = sanitized_details
        else:
            self.details = {}

    def __str__(self) -> str:
        parts = [f"[{self.code}] {self.raw_message}"]
        context = []
        if self.source_id:
            context.append(f"source_id={self.source_id}")
        if self.connector_type:
            context.append(f"connector_type={self.connector_type}")
        context.append(f"class={self.error_class}")
        if context:
            parts.append(f"({', '.join(context)})")
        return " ".join(parts)


class ConnectorTimeoutError(ConnectorError):
    """Connector fetch operation timed out."""

    def __init__(
        self,
        message: str = "Connector operation timed out",
        *,
        code: str = "SOURCE_TIMEOUT",
        source_id: str | None = None,
        connector_type: ConnectorType | str | None = None,
        retry_after_seconds: float | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        merged_details = dict(details or {})
        if retry_after_seconds is not None:
            merged_details["retry_after_seconds"] = retry_after_seconds
        super().__init__(
            message,
            code=code,
            source_id=source_id,
            connector_type=connector_type,
            error_class=ConnectorErrorClass.TRANSIENT,
            details=merged_details,
        )
        self.retry_after_seconds = retry_after_seconds
