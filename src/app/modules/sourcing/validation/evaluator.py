"""Deterministic three-stage record evaluator and issue composition.

Governed by:
- SDD 004 §6: structural, normalization, and record-local business stages.
- SDD 004 §7: issue type, deterministic keys, sanitized messages and excerpts.
- M2-D04 / M2-D05: quarantine status, canonical payloads, versioned outcomes.
- INV-014: outcomes trace to run, record, and rule.

The evaluator is pure with respect to its inputs: it performs no I/O, clock
reads, database access, or randomness. The pipeline owns persistence.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from app.modules.sourcing.persistence import (
    IssueType,
    SourceRecord,
    ValidationIssueDraft,
    ValidationStatus,
)
from app.modules.sourcing.validation.catalog import (
    RULES_BY_CODE,
    Rule,
    RuleSeverity,
    RuleStage,
    rules_for,
)
from app.modules.sourcing.validation.config import EntitySchema, FieldDeclaration
from app.modules.sourcing.validation.errors import SourcingValidationContractError
from app.modules.sourcing.validation.messages import render_message, sanitize_excerpt
from app.modules.sourcing.validation.normalize import (
    CANONICAL_FIELDS,
    UPPERCASE_TEXT_TARGETS,
    canonical_decimal,
    field_kind,
    normalize_identifier,
    normalize_supplier_key,
    normalize_text,
    parse_currency,
    parse_date,
    parse_decimal,
    parse_enum,
    parse_timestamp,
)
from app.modules.sourcing.validation.types import ParsedField, RuleContext, RuleFinding

_MAX_ISSUE_KEY: Final[int] = 128
_DATE_ORDER_FIELDS: Final[Mapping[str, tuple[str, str]]] = {
    "requisition": ("requested_on", "needed_by"),
    "purchase_order": ("ordered_on", "committed_delivery_date"),
}


@dataclass(frozen=True)
class EvaluationOutcome:
    """Terminal status, optional canonical payload, and composed issues."""

    status: str
    normalized_payload: Mapping[str, Any] | None
    issues: tuple[ValidationIssueDraft, ...]


@dataclass(frozen=True)
class _Finding:
    rule: Rule
    finding: RuleFinding


def evaluate_record(record: SourceRecord, schema: EntitySchema) -> EvaluationOutcome:
    """Evaluate one captured record through all three rule stages."""
    ctx = RuleContext(
        entity_type=record.entity_type,
        raw_payload=dict(record.raw_payload),
        schema=schema,
        external_record_id=record.external_record_id,
        source_timestamp=record.source_timestamp,
    )

    findings: list[_Finding] = []
    flagged: set[str | None] = set()
    for rule in rules_for(record.entity_type, RuleStage.STRUCTURAL):
        for finding in rule.evaluate(ctx):
            if finding.field_name in flagged:
                continue
            flagged.add(finding.field_name)
            findings.append(_Finding(rule, finding))
    if _has_error(findings):
        return _outcome(
            record,
            ctx,
            findings,
            status=ValidationStatus.QUARANTINED.value,
            payload=None,
        )

    _populate_parsed(ctx)

    for rule in rules_for(record.entity_type, RuleStage.NORMALIZATION):
        for finding in rule.evaluate(ctx):
            findings.append(_Finding(rule, finding))
    if _has_error(findings):
        return _outcome(
            record,
            ctx,
            findings,
            status=ValidationStatus.QUARANTINED.value,
            payload=None,
        )

    payload = _build_payload(ctx)
    ctx.normalized = payload
    findings.extend(_post_normalization_findings(ctx))
    if _has_error(findings):
        return _outcome(
            record,
            ctx,
            findings,
            status=ValidationStatus.QUARANTINED.value,
            payload=None,
        )

    for rule in rules_for(record.entity_type, RuleStage.BUSINESS):
        for finding in rule.evaluate(ctx):
            findings.append(_Finding(rule, finding))

    if _has_error(findings):
        status = ValidationStatus.QUARANTINED.value
    elif findings:
        status = ValidationStatus.WARNING.value
    else:
        status = ValidationStatus.VALID.value
    return _outcome(record, ctx, findings, status=status, payload=payload)


def _has_error(findings: Sequence[_Finding]) -> bool:
    return any(item.rule.severity is RuleSeverity.ERROR for item in findings)


def _outcome(
    record: SourceRecord,
    ctx: RuleContext,
    findings: Sequence[_Finding],
    *,
    status: str,
    payload: Mapping[str, Any] | None,
) -> EvaluationOutcome:
    return EvaluationOutcome(
        status=status,
        normalized_payload=payload,
        issues=_compose_issues(record, ctx, findings),
    )


def _populate_parsed(ctx: RuleContext) -> None:
    reverse = {declaration.target: source for source, declaration in ctx.schema.fields.items()}
    targets = list(CANONICAL_FIELDS.get(ctx.entity_type, ()))
    if "external_record_id" in reverse:
        targets.append("external_record_id")
    if "source_timestamp" in reverse:
        targets.append("source_timestamp")

    for target in targets:
        source_field = reverse.get(target)
        if source_field is None:
            continue
        declaration = ctx.schema.fields[source_field]
        ctx.parsed[target] = _parse_field(ctx, declaration, ctx.raw_payload.get(source_field))


def _parse_field(ctx: RuleContext, declaration: FieldDeclaration, raw: Any) -> ParsedField:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return ParsedField(raw_value=raw, value=None, failure=None)

    if declaration.type == "string":
        if not isinstance(raw, str):
            return ParsedField(raw, None, "INVALID")
        kind = field_kind(ctx.entity_type, declaration.target)
        if kind == "currency":
            value, failure = parse_currency(raw)
            return ParsedField(raw, value, failure)
        if declaration.target == "external_record_id":
            return ParsedField(raw, normalize_identifier(raw, "preserve"), None)
        if kind in ("identifier", "reference"):
            return ParsedField(raw, normalize_identifier(raw, declaration.case), None)
        normalized = normalize_text(raw)
        if declaration.target in UPPERCASE_TEXT_TARGETS:
            normalized = normalized.upper()
        return ParsedField(raw, normalized, None)

    if declaration.type == "enum":
        value, failure = parse_enum(raw, declaration.enum or {})
        return ParsedField(raw, value, failure)

    if declaration.type == "date":
        value, failure = parse_date(raw, declaration.formats)
        return ParsedField(raw, value, failure)

    if declaration.type == "timestamp":
        value, failure = parse_timestamp(
            raw, declaration.formats, declaration.timezone or ctx.schema.timezone
        )
        return ParsedField(raw, value, failure)

    if declaration.type == "decimal":
        convention = declaration.decimal or ctx.schema.decimal
        decimal_value, failure = parse_decimal(
            raw, separator=convention.separator, thousands=convention.thousands
        )
        canonical = (
            canonical_decimal(decimal_value)
            if decimal_value is not None and failure is None
            else None
        )
        return ParsedField(raw, canonical, failure)

    if declaration.type == "integer":
        if isinstance(raw, bool) or not isinstance(raw, int):
            return ParsedField(raw, None, "INVALID")
        return ParsedField(raw, raw, None)

    if declaration.type == "boolean":
        if not isinstance(raw, bool):
            return ParsedField(raw, None, "INVALID")
        return ParsedField(raw, raw, None)

    return ParsedField(raw, None, "INVALID")


def _build_payload(ctx: RuleContext) -> Mapping[str, Any]:
    payload: dict[str, Any] = {}
    for target in CANONICAL_FIELDS.get(ctx.entity_type, ()):
        parsed = ctx.parsed.get(target)
        if parsed is None or parsed.failure is not None or parsed.value is None:
            continue
        declaration = _declaration_for(ctx.schema, target)
        if parsed.value == "" and (declaration is None or not declaration.required):
            continue
        payload[target] = parsed.value

    if ctx.entity_type == "supplier":
        name = payload.get("name")
        if isinstance(name, str) and name:
            payload["normalized_name_key"] = normalize_supplier_key(name)
    return payload


def _post_normalization_findings(ctx: RuleContext) -> Sequence[_Finding]:
    findings: list[_Finding] = []
    for target, value in ctx.normalized.items():
        declaration = _declaration_for(ctx.schema, target)
        if declaration is None or not isinstance(value, str):
            continue
        if declaration.required and not value:
            findings.append(_Finding(RULES_BY_CODE["STRUCT_REQUIRED_FIELD"], RuleFinding(target)))
            continue
        if declaration.max_length is not None and len(value) > declaration.max_length:
            findings.append(
                _Finding(RULES_BY_CODE["STRUCT_MAX_LENGTH"], RuleFinding(target, value))
            )
        if declaration.pattern is not None and re.fullmatch(declaration.pattern, value) is None:
            findings.append(
                _Finding(RULES_BY_CODE["STRUCT_INVALID_FORMAT"], RuleFinding(target, value))
            )
    return findings


def _declaration_for(schema: EntitySchema, target: str | None) -> FieldDeclaration | None:
    if target is None:
        return None
    for declaration in schema.fields.values():
        if declaration.target == target:
            return declaration
    return None


def _compose_issues(
    record: SourceRecord,
    ctx: RuleContext,
    findings: Sequence[_Finding],
) -> tuple[ValidationIssueDraft, ...]:
    counters: dict[tuple[str, str | None], int] = {}
    issues: list[ValidationIssueDraft] = []
    for item in findings:
        rule = item.rule
        finding = item.finding
        field = finding.field_name
        ordinal = counters.get((rule.code, field), 0)
        counters[(rule.code, field)] = ordinal + 1

        token = field if field else "-"
        issue_key = f"{IssueType.VALIDATION.value}:{rule.code}:{token}:{ordinal}"
        if len(issue_key) > _MAX_ISSUE_KEY:
            raise SourcingValidationContractError(
                f"Issue key exceeds {_MAX_ISSUE_KEY} characters for rule '{rule.code}'."
            )

        declaration = _declaration_for(ctx.schema, field)
        raw_value: str | None = None
        if finding.raw_value is not None and (declaration is None or not declaration.sensitive):
            raw_value = sanitize_excerpt(finding.raw_value)

        message = render_message(
            rule.code,
            field=field,
            **_message_params(rule, ctx, declaration),
        )
        issues.append(
            ValidationIssueDraft(
                ingestion_run_id=record.ingestion_run_id,
                source_record_id=record.id,
                issue_key=issue_key,
                issue_type=IssueType.VALIDATION.value,
                rule_code=rule.code,
                severity=rule.severity.value,
                field_name=field,
                message=message,
                raw_value=raw_value,
            )
        )
    return tuple(issues)


def _message_params(
    rule: Rule,
    ctx: RuleContext,
    declaration: FieldDeclaration | None,
) -> Mapping[str, object]:
    if rule.code == "STRUCT_INVALID_TYPE":
        return {"expected_type": declaration.type if declaration else "unknown"}
    if rule.code == "STRUCT_MAX_LENGTH":
        return {"max_length": declaration.max_length if declaration else 0}
    if rule.code == "BUSINESS_DATE_ORDER":
        fields = _DATE_ORDER_FIELDS.get(ctx.entity_type)
        if fields is None:
            return {"earlier": "earlier", "later": "later"}
        return {"earlier": fields[0], "later": fields[1]}
    return {}
