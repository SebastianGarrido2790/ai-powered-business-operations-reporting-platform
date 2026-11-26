"""Declarative SLA catalog models, loader, and deterministic resolution.

Governed by:
- M3-D02.1: SLA thresholds are configuration, not code, and no business target
  is invented before the OD-03 catalog review.
- INV-003: authoritative rules are deterministic and inspectable.
- INV-016: configuration contains no secrets; diagnostics are sanitized.
- ADR-009: resolution is deterministic code, not a model or workflow prompt.

The catalog is immutable. Loading validates the whole file atomically and
raises `SlaConfigError` on any failure; module startup converts that failure
into a degraded health facet without blocking ingestion.
"""

import hashlib
import re
from collections.abc import Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Final, Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.modules.sourcing.config.sources import SourceRegistry
from app.modules.sourcing.ingestion.record_key import canonical_json

_SLA_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9][A-Z0-9_-]*$")
_CATALOG_VERSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d+\.\d+\.\d+$")
_TARGET_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\d+(\.\d+)?$")


class SlaConfigError(Exception):
    """The SLA catalog is missing, malformed, or inconsistent.

    `code` is a stable diagnostic token safe to expose through module health.
    The message names the failing field path when available and never includes
    raw values, file paths, or stack traces.
    """

    def __init__(self, message: str, *, code: str = "SLA_CONFIG_INVALID") -> None:
        self.code = code
        super().__init__(message)


class SlaMetric(StrEnum):
    """Closed set of metrics an SLA rule may target."""

    OTD_RATE = "OTD_RATE"
    MAX_LEAD_TIME_DAYS = "MAX_LEAD_TIME_DAYS"
    MAX_QUOTE_RESPONSE_DAYS = "MAX_QUOTE_RESPONSE_DAYS"


_TARGET_METRICS = frozenset({SlaMetric.MAX_LEAD_TIME_DAYS, SlaMetric.MAX_QUOTE_RESPONSE_DAYS})


class _FrozenModel(BaseModel):
    """Immutable model base that rejects undeclared keys."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SupplierSlaScope(_FrozenModel):
    """An SLA scoped to one supplier from one authoritative origin."""

    type: Literal["supplier"]
    origin_source_id: str
    supplier_external_id: str

    @field_validator("origin_source_id", "supplier_external_id")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be non-empty")
        return value


class CategorySlaScope(_FrozenModel):
    """An SLA scoped to one already-canonical supplier category."""

    type: Literal["category"]
    category: str

    @field_validator("category")
    @classmethod
    def _canonical_category(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be non-empty")
        if value != value.upper():
            raise ValueError("must already be uppercase")
        return value


SlaScope = Annotated[SupplierSlaScope | CategorySlaScope, Field(discriminator="type")]


def _scope_identity(scope: SupplierSlaScope | CategorySlaScope) -> tuple[str, ...]:
    if isinstance(scope, SupplierSlaScope):
        return ("supplier", scope.origin_source_id, scope.supplier_external_id)
    return ("category", scope.category)


class SlaRule(_FrozenModel):
    """One effective-dated SLA target for a supplier or category scope."""

    sla_id: str
    scope: SlaScope
    metric: SlaMetric
    target: Decimal
    effective_from: date
    effective_to: date | None = None
    owner: str

    @field_validator("sla_id")
    @classmethod
    def _valid_sla_id(cls, value: str) -> str:
        if _SLA_ID_PATTERN.fullmatch(value) is None:
            raise ValueError("must match ^[A-Z0-9][A-Z0-9_-]*$")
        return value

    @field_validator("owner")
    @classmethod
    def _valid_owner(cls, value: str) -> str:
        if not value.strip() or len(value) > 255:
            raise ValueError("must be non-empty text of at most 255 characters")
        return value

    @field_validator("target", mode="before")
    @classmethod
    def _string_decimal_target(cls, value: object) -> Decimal:
        if isinstance(value, bool) or not isinstance(value, str):
            raise ValueError("must be a decimal string")
        if _TARGET_PATTERN.fullmatch(value) is None:
            raise ValueError("must match ^\\d+(\\.\\d+)?$")
        try:
            return Decimal(value)
        except InvalidOperation:
            raise ValueError("must be a decimal string") from None

    @model_validator(mode="after")
    def _valid_window_and_target(self) -> "SlaRule":
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        if self.metric is SlaMetric.OTD_RATE:
            if not (Decimal(0) < self.target <= Decimal(1)):
                raise ValueError("OTD_RATE target must be greater than 0 and at most 1")
        elif self.metric in _TARGET_METRICS:
            if self.target < 0 or self.target != self.target.to_integral_value():
                raise ValueError("maximum metric targets must be integral and non-negative")
        return self


class _SlaFile(_FrozenModel):
    """Raw `config/sourcing/slas.yaml` shape before identity is derived."""

    version: Literal[1]
    catalog_version: str
    slas: tuple[SlaRule, ...]

    @field_validator("catalog_version")
    @classmethod
    def _valid_catalog_version(cls, value: str) -> str:
        if _CATALOG_VERSION_PATTERN.fullmatch(value) is None:
            raise ValueError("must match ^\\d+\\.\\d+\\.\\d+$")
        return value


class SlaCatalog(_FrozenModel):
    """Immutable SLA catalog with deterministic resolution and version identity."""

    version: Literal[1]
    catalog_version: str
    rules: tuple[SlaRule, ...]
    catalog_hash: str
    resolved_version: str

    @model_validator(mode="after")
    def _unique_and_non_overlapping(self) -> "SlaCatalog":
        ids = [rule.sla_id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("sla_id values must be unique")

        groups: dict[tuple[str, ...], list[SlaRule]] = {}
        for rule in self.rules:
            groups.setdefault((*_scope_identity(rule.scope), rule.metric.value), []).append(rule)

        for group in groups.values():
            ordered = sorted(group, key=lambda rule: rule.effective_from)
            for previous, following in zip(ordered, ordered[1:], strict=False):
                if (
                    previous.effective_to is None
                    or following.effective_from <= previous.effective_to
                ):
                    raise ValueError(
                        f"SLA rules for the same scope and metric overlap at '{following.sla_id}'"
                    )
        return self

    def resolve(
        self,
        *,
        as_of: date,
        metric: SlaMetric,
        origin_source_id: str,
        supplier_external_id: str | None,
        category: str | None,
    ) -> SlaRule | None:
        """Return the active supplier rule, else the active category rule, else None."""
        supplier_rule = None
        if supplier_external_id is not None:
            supplier_rule = self._find_active(
                as_of=as_of,
                metric=metric,
                identity=("supplier", origin_source_id, supplier_external_id),
            )
        if supplier_rule is not None:
            return supplier_rule
        if category is not None:
            return self._find_active(
                as_of=as_of,
                metric=metric,
                identity=("category", category),
            )
        return None

    def _find_active(
        self,
        *,
        as_of: date,
        metric: SlaMetric,
        identity: tuple[str, ...],
    ) -> SlaRule | None:
        for rule in self.rules:
            if rule.metric is not metric or _scope_identity(rule.scope) != identity:
                continue
            assert rule.effective_to is None or rule.effective_to >= rule.effective_from
            if rule.effective_from <= as_of and (
                rule.effective_to is None or as_of <= rule.effective_to
            ):
                return rule
        return None


def compute_catalog_identity(catalog_version: str, rules: Sequence[SlaRule]) -> tuple[str, str]:
    """Return `(catalog_hash, resolved_version)` for an ordered-independent rule set."""
    ordered = sorted(rules, key=lambda rule: rule.sla_id)
    payload = {"rules": [rule.model_dump(mode="json") for rule in ordered]}
    digest = hashlib.sha256(canonical_json(payload)).hexdigest()
    return digest, f"{catalog_version}+{digest[:12]}"


def load_sla_catalog(path: Path, source_registry: SourceRegistry) -> SlaCatalog:
    """Load, cross-check, and freeze the SLA catalog atomically."""
    if not path.is_file():
        raise SlaConfigError(
            "SLA configuration file not found.",
            code="SLA_CONFIG_MISSING",
        )

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SlaConfigError(
            "SLA configuration contains malformed YAML.",
            code="SLA_CONFIG_MALFORMED",
        ) from exc

    if not isinstance(raw, dict):
        raise SlaConfigError(
            "SLA configuration must contain a top-level mapping.",
            code="SLA_CONFIG_INVALID",
        )

    try:
        file_model = _SlaFile.model_validate(raw)
    except ValidationError as exc:
        summary = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise SlaConfigError(
            f"SLA configuration is invalid: {summary}",
            code="SLA_CONFIG_INVALID",
        ) from exc

    _validate_supplier_scopes(file_model.slas, source_registry)

    try:
        catalog_hash, resolved_version = compute_catalog_identity(
            file_model.catalog_version, file_model.slas
        )
        return SlaCatalog(
            version=file_model.version,
            catalog_version=file_model.catalog_version,
            rules=file_model.slas,
            catalog_hash=catalog_hash,
            resolved_version=resolved_version,
        )
    except ValidationError as exc:
        summary = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise SlaConfigError(
            f"SLA catalog is invalid: {summary}",
            code="SLA_CONFIG_INVALID",
        ) from exc


def _validate_supplier_scopes(rules: Sequence[SlaRule], source_registry: SourceRegistry) -> None:
    for rule in rules:
        scope = rule.scope
        if not isinstance(scope, SupplierSlaScope):
            continue
        if scope.origin_source_id not in source_registry:
            raise SlaConfigError(
                f"SLA rule '{rule.sla_id}' references an unknown origin source.",
                code="SLA_CONFIG_INVALID",
            )
        definition = source_registry.get(scope.origin_source_id)
        if "supplier" not in definition.authoritative_entities:
            raise SlaConfigError(
                f"SLA rule '{rule.sla_id}' references an origin source that does not "
                "own supplier data.",
                code="SLA_CONFIG_INVALID",
            )
