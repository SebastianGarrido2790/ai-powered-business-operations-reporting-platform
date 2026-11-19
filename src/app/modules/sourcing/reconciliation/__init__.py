"""Sourcing reconciliation: fingerprint, duplicates, identity, links, authority.

Governed by:
- SDD 005: content fingerprint, source-scoped duplicate detection, the
  deterministic identity cascade, foreign-key link resolution, field-level
  source authority, and the page-composing pipeline.
- ADR-003: curated entities with immutable origin identity and provenance.
- ADR-009: deterministic matching and authority; no fuzzy or ML auto-merging.
- M2-D06: reconciliation status and authority update modes.
"""

from app.modules.sourcing.reconciliation.errors import (
    SourcingReconciliationContractError,
)
from app.modules.sourcing.reconciliation.fingerprint import content_fingerprint
from app.modules.sourcing.reconciliation.pipeline import ReconciliationPipeline
from app.modules.sourcing.reconciliation.types import (
    ConflictFinding,
    IdentityResolution,
    RecordReconciliation,
)

__all__ = [
    "ConflictFinding",
    "IdentityResolution",
    "RecordReconciliation",
    "ReconciliationPipeline",
    "SourcingReconciliationContractError",
    "content_fingerprint",
]
