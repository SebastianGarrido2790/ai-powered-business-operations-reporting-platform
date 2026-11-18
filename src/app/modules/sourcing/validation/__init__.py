"""Deterministic Sourcing validation, normalization, and quarantine.

Governed by:
- SDD 004: catalog, configuration, evaluation, issues, and pipeline.
- M2-D04 / M2-D04.1 / M2-D05: per-record outcomes, versioned code rules, and
  canonical values.
- ADR-009: deterministic code owns enforceable business rules.
"""

from app.modules.sourcing.validation.catalog import (
    RULES,
    RULES_BY_CODE,
    RULESET_VERSION,
    Rule,
    RuleSeverity,
    RuleStage,
    rules_for,
)
from app.modules.sourcing.validation.config import (
    DecimalConvention,
    EntitySchema,
    FieldDeclaration,
    ValidationConfig,
    load_validation_config,
    section_version,
)
from app.modules.sourcing.validation.errors import (
    SourcingValidationConfigError,
    SourcingValidationContractError,
)
from app.modules.sourcing.validation.evaluator import EvaluationOutcome, evaluate_record
from app.modules.sourcing.validation.messages import (
    EXCERPT_LIMIT,
    TEMPLATES,
    render_message,
    sanitize_excerpt,
)
from app.modules.sourcing.validation.normalize import (
    CANONICAL_FIELDS,
    CANONICAL_MAX_LENGTHS,
    SUPPORTED_CURRENCIES,
    canonical_decimal,
    normalize_identifier,
    normalize_supplier_key,
    normalize_text,
    parse_currency,
    parse_date,
    parse_decimal,
    parse_enum,
    parse_timestamp,
)
from app.modules.sourcing.validation.pipeline import (
    PageOutcome,
    RecordOutcome,
    ValidationNormalizationPipeline,
)
from app.modules.sourcing.validation.types import ParsedField, RuleContext, RuleFinding

__all__ = [
    "CANONICAL_FIELDS",
    "CANONICAL_MAX_LENGTHS",
    "EXCERPT_LIMIT",
    "RULES",
    "RULESET_VERSION",
    "RULES_BY_CODE",
    "SUPPORTED_CURRENCIES",
    "TEMPLATES",
    "DecimalConvention",
    "EntitySchema",
    "EvaluationOutcome",
    "FieldDeclaration",
    "ParsedField",
    "PageOutcome",
    "RecordOutcome",
    "Rule",
    "RuleContext",
    "RuleFinding",
    "RuleSeverity",
    "RuleStage",
    "SourcingValidationConfigError",
    "SourcingValidationContractError",
    "ValidationConfig",
    "ValidationNormalizationPipeline",
    "canonical_decimal",
    "evaluate_record",
    "load_validation_config",
    "normalize_identifier",
    "normalize_supplier_key",
    "normalize_text",
    "parse_currency",
    "parse_date",
    "parse_decimal",
    "parse_enum",
    "parse_timestamp",
    "render_message",
    "rules_for",
    "sanitize_excerpt",
    "section_version",
]
