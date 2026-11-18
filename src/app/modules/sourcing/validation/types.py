"""Core value types for deterministic Sourcing validation and normalization.

Governed by:
- SDD 004 §4.1 / §6: rule context, findings, and parsed-field state.
- ADR-009: rules are pure functions of captured data and configuration.
- INV-010: validation is deterministic and testable.

`RuleContext` is mutable evaluation state. Structural, normalization, and
business rules read it and never mutate it; the evaluator owns the lifecycle.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.modules.sourcing.validation.config import EntitySchema


@dataclass(frozen=True)
class RuleFinding:
    """A single rule finding before issue composition.

    `field_name` is the canonical target when the rule applies to one field and
    `None` for record-level findings. `raw_value` is the offending raw value;
    the evaluator sanitizes, bounds, and suppresses it before persistence.
    """

    field_name: str | None
    raw_value: str | None = None


@dataclass(frozen=True)
class ParsedField:
    """One declared field parsed once during normalization.

    `failure` is an internal token (`INVALID`, `AMBIGUOUS`, `NO_TIMEZONE`,
    `AMBIGUOUS_SEPARATOR`, `PRECISION`, `RANGE`, `UNKNOWN`) mapped to a catalog
    code by the normalization rules. It is never persisted or rendered.
    """

    raw_value: Any
    value: Any | None
    failure: str | None = None


@dataclass
class RuleContext:
    """Evaluation state shared by the three rule stages."""

    entity_type: str
    raw_payload: Mapping[str, Any]
    schema: "EntitySchema"
    external_record_id: str | None
    source_timestamp: datetime | None
    normalized: Mapping[str, Any] = field(default_factory=dict)
    parsed: dict[str, ParsedField] = field(default_factory=dict)
