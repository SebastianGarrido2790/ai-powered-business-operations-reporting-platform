"""Reconciliation issue catalog and bounded evidence rendering.

Governed by:
- SDD 005 §9: ten approved codes, all `WARNING` severity, fixed message
  templates, deterministic `<type>:<code>:<field>:0` keys (at most 128
  characters), and evidence sanitized through SDD 004's `sanitize_excerpt`.
- INV-016: no raw payload, secret, credential, or stack trace is persisted.
"""

from typing import Final
from uuid import UUID

from app.modules.sourcing.persistence.records import (
    IssueSeverity,
    IssueType,
    ValidationIssueDraft,
)
from app.modules.sourcing.reconciliation.errors import SourcingReconciliationContractError
from app.modules.sourcing.validation.messages import sanitize_excerpt

_MAX_ISSUE_KEY: Final[int] = 128

_MESSAGES: Final[dict[str, str]] = {
    "DUPLICATE_EXACT_RECORD": (
        "Record duplicates an earlier record with the same source identity in this run."
    ),
    "DUPLICATE_POTENTIAL_CONTENT": (
        "Record content matches {n} earlier record(s) under this source."
    ),
    "CONFLICT_IDENTITY_CONTENT": (
        "Source identity was observed with different content earlier in this run."
    ),
    "CONFLICT_SOURCE_AUTHORITY": (
        "A non-authoritative source value differs from the stored value; the stored value was kept."
    ),
    "RECONCILIATION_IDENTITY_AMBIGUOUS": (
        "{n} curated records match the business identifier; no curated row was written."
    ),
    "RECONCILIATION_SUPPLIER_UNRESOLVED": (
        "The supplier reference did not resolve to a curated supplier."
    ),
    "RECONCILIATION_REQUISITION_UNRESOLVED": (
        "The requisition reference did not resolve to a curated requisition."
    ),
    "RECONCILIATION_REQUISITION_AMBIGUOUS": ("{n} curated requisitions match the reference."),
    "RECONCILIATION_PURCHASE_ORDER_UNRESOLVED": (
        "The purchase-order reference did not resolve to a curated purchase order."
    ),
    "RECONCILIATION_PURCHASE_ORDER_AMBIGUOUS": ("{n} curated purchase orders match the reference."),
}

_ISSUE_TYPES: Final[dict[str, str]] = {
    "DUPLICATE_EXACT_RECORD": IssueType.DUPLICATE.value,
    "DUPLICATE_POTENTIAL_CONTENT": IssueType.DUPLICATE.value,
    "CONFLICT_IDENTITY_CONTENT": IssueType.CONFLICT.value,
    "CONFLICT_SOURCE_AUTHORITY": IssueType.CONFLICT.value,
    "RECONCILIATION_IDENTITY_AMBIGUOUS": IssueType.RECONCILIATION.value,
    "RECONCILIATION_SUPPLIER_UNRESOLVED": IssueType.RECONCILIATION.value,
    "RECONCILIATION_REQUISITION_UNRESOLVED": IssueType.RECONCILIATION.value,
    "RECONCILIATION_REQUISITION_AMBIGUOUS": IssueType.RECONCILIATION.value,
    "RECONCILIATION_PURCHASE_ORDER_UNRESOLVED": IssueType.RECONCILIATION.value,
    "RECONCILIATION_PURCHASE_ORDER_AMBIGUOUS": IssueType.RECONCILIATION.value,
}


def codes() -> tuple[str, ...]:
    """Return the approved catalog codes, in catalog order."""
    return tuple(_MESSAGES)


def issue_key(issue_type: str, code: str, field_name: str | None) -> str:
    """Build the deterministic key and enforce the 128-character bound."""
    key = f"{issue_type}:{code}:{field_name if field_name else '-'}:0"
    if len(key) > _MAX_ISSUE_KEY:
        raise SourcingReconciliationContractError(
            f"Issue key for '{code}' exceeds {_MAX_ISSUE_KEY} characters.",
            code="RECONCILIATION_ISSUE_KEY",
        )
    return key


def _build(
    code: str,
    *,
    ingestion_run_id: UUID,
    source_record_id: UUID,
    field_name: str | None,
    evidence: str | None = None,
    message_params: dict[str, object] | None = None,
) -> ValidationIssueDraft:
    issue_type = _ISSUE_TYPES[code]
    message = _MESSAGES[code].format(**(message_params or {}))
    return ValidationIssueDraft(
        ingestion_run_id=ingestion_run_id,
        source_record_id=source_record_id,
        issue_key=issue_key(issue_type, code, field_name),
        issue_type=issue_type,
        rule_code=code,
        severity=IssueSeverity.WARNING.value,
        message=message,
        field_name=field_name,
        raw_value=sanitize_excerpt(evidence) if evidence is not None else None,
    )


def duplicate_exact_record(
    *,
    ingestion_run_id: UUID,
    source_record_id: UUID,
    earlier_record_key: str,
) -> ValidationIssueDraft:
    return _build(
        "DUPLICATE_EXACT_RECORD",
        ingestion_run_id=ingestion_run_id,
        source_record_id=source_record_id,
        field_name=None,
        evidence=f"earlier={earlier_record_key}",
    )


def duplicate_potential_content(
    *,
    ingestion_run_id: UUID,
    source_record_id: UUID,
    earliest_record_key: str,
    matches: int,
) -> ValidationIssueDraft:
    return _build(
        "DUPLICATE_POTENTIAL_CONTENT",
        ingestion_run_id=ingestion_run_id,
        source_record_id=source_record_id,
        field_name=None,
        evidence=f"earliest={earliest_record_key}; matches={matches}",
        message_params={"n": matches},
    )


def conflict_identity_content(
    *,
    ingestion_run_id: UUID,
    source_record_id: UUID,
    earlier_record_key: str,
) -> ValidationIssueDraft:
    return _build(
        "CONFLICT_IDENTITY_CONTENT",
        ingestion_run_id=ingestion_run_id,
        source_record_id=source_record_id,
        field_name=None,
        evidence=f"earlier={earlier_record_key}",
    )


def conflict_source_authority(
    *,
    ingestion_run_id: UUID,
    source_record_id: UUID,
    field_name: str,
    stored: object,
    incoming: object,
) -> ValidationIssueDraft:
    return _build(
        "CONFLICT_SOURCE_AUTHORITY",
        ingestion_run_id=ingestion_run_id,
        source_record_id=source_record_id,
        field_name=field_name,
        evidence=f"stored={stored}; incoming={incoming}",
    )


def identity_ambiguous(
    *,
    ingestion_run_id: UUID,
    source_record_id: UUID,
    business_identifier: str,
    candidates: int,
) -> ValidationIssueDraft:
    return _build(
        "RECONCILIATION_IDENTITY_AMBIGUOUS",
        ingestion_run_id=ingestion_run_id,
        source_record_id=source_record_id,
        field_name=business_identifier,
        evidence=f"candidates={candidates}",
        message_params={"n": candidates},
    )


_LINK_UNRESOLVED_CODES: Final[dict[str, str]] = {
    "supplier_id": "RECONCILIATION_SUPPLIER_UNRESOLVED",
    "requisition_id": "RECONCILIATION_REQUISITION_UNRESOLVED",
    "purchase_order_id": "RECONCILIATION_PURCHASE_ORDER_UNRESOLVED",
}
_LINK_AMBIGUOUS_CODES: Final[dict[str, str]] = {
    "requisition_id": "RECONCILIATION_REQUISITION_AMBIGUOUS",
    "purchase_order_id": "RECONCILIATION_PURCHASE_ORDER_AMBIGUOUS",
}


def link_unresolved(
    *,
    ingestion_run_id: UUID,
    source_record_id: UUID,
    link: str,
    reference: str | None,
) -> ValidationIssueDraft:
    return _build(
        _LINK_UNRESOLVED_CODES[link],
        ingestion_run_id=ingestion_run_id,
        source_record_id=source_record_id,
        field_name=_LINK_FIELD_TOKENS[link],
        evidence=f"reference={reference}" if reference else None,
    )


def link_ambiguous(
    *,
    ingestion_run_id: UUID,
    source_record_id: UUID,
    link: str,
    candidates: int,
) -> ValidationIssueDraft:
    return _build(
        _LINK_AMBIGUOUS_CODES[link],
        ingestion_run_id=ingestion_run_id,
        source_record_id=source_record_id,
        field_name=_LINK_FIELD_TOKENS[link],
        evidence=f"candidates={candidates}",
        message_params={"n": candidates},
    )


_LINK_FIELD_TOKENS: Final[dict[str, str]] = {
    "supplier_id": "supplier_code",
    "requisition_id": "requisition_number",
    "purchase_order_id": "purchase_order_number",
}
