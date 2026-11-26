"""Declarative SLA catalog loading and resolution tests for SDD 001 Stage 1."""

from datetime import date
from pathlib import Path

import pytest
from support.sla_cases import (
    catalog,
    category_scope,
    load,
    rule,
    supplier_scope,
    write_catalog,
)

from app.modules.sourcing.config.slas import SlaConfigError, SlaMetric


def test_empty_catalog_is_valid_and_has_a_stable_identity(tmp_path: Path) -> None:
    """An empty catalog loads, resolves to NOT_APPLICABLE, and carries a hash."""
    loaded = load(write_catalog(tmp_path / "slas.yaml", catalog()))

    assert loaded.version == 1
    assert loaded.catalog_version == "1.0.0"
    assert loaded.rules == ()
    assert len(loaded.catalog_hash) == 64
    assert loaded.resolved_version == f"1.0.0+{loaded.catalog_hash[:12]}"
    assert (
        loaded.resolve(
            as_of=date(2026, 1, 1),
            metric=SlaMetric.OTD_RATE,
            origin_source_id="erp_master_data",
            supplier_external_id="SUP-1",
            category="ELECTRONICS",
        )
        is None
    )


def test_populated_catalog_preserves_rules_and_targets(tmp_path: Path) -> None:
    """A valid rule loads with an exact decimal target and closed metric."""
    loaded = load(
        write_catalog(
            tmp_path / "slas.yaml",
            catalog(
                rule(
                    sla_id="OTD-SUP-1",
                    metric="OTD_RATE",
                    target="0.95",
                    effective_to="2026-12-31",
                )
            ),
        )
    )

    assert len(loaded.rules) == 1
    loaded_rule = loaded.rules[0]
    assert loaded_rule.sla_id == "OTD-SUP-1"
    assert loaded_rule.metric is SlaMetric.OTD_RATE
    assert str(loaded_rule.target) == "0.95"
    assert loaded_rule.effective_to == date(2026, 12, 31)


def test_missing_file_is_rejected_with_a_stable_code(tmp_path: Path) -> None:
    """A missing catalog fails atomically as SLA_CONFIG_MISSING."""
    with pytest.raises(SlaConfigError) as excinfo:
        load(tmp_path / "absent.yaml")
    assert excinfo.value.code == "SLA_CONFIG_MISSING"


def test_malformed_yaml_is_rejected_with_a_stable_code(tmp_path: Path) -> None:
    """Malformed YAML fails as SLA_CONFIG_MALFORMED."""
    path = write_catalog(tmp_path / "slas.yaml", {}, raw="version: 1\nslas: [\n")
    with pytest.raises(SlaConfigError) as excinfo:
        load(path)
    assert excinfo.value.code == "SLA_CONFIG_MALFORMED"


def test_schema_and_rule_failures_are_rejected_atomically(tmp_path: Path) -> None:
    """Unknown keys and invalid rule shapes fail as SLA_CONFIG_INVALID."""
    unknown_key = {**catalog(), "unexpected": True}
    with pytest.raises(SlaConfigError) as excinfo:
        load(write_catalog(tmp_path / "unknown.yaml", unknown_key))
    assert excinfo.value.code == "SLA_CONFIG_INVALID"

    invalid_owner = catalog(rule(owner=""))
    with pytest.raises(SlaConfigError) as excinfo:
        load(write_catalog(tmp_path / "owner.yaml", invalid_owner))
    assert excinfo.value.code == "SLA_CONFIG_INVALID"

    invalid_catalog_version = catalog(catalog_version="1.0")
    with pytest.raises(SlaConfigError) as excinfo:
        load(write_catalog(tmp_path / "version.yaml", invalid_catalog_version))
    assert excinfo.value.code == "SLA_CONFIG_INVALID"


@pytest.mark.parametrize("target", [0.95, 1, None, True])
def test_target_must_be_a_yaml_string(tmp_path: Path, target: object) -> None:
    """Floats and non-strings are rejected before decimal conversion."""
    path = write_catalog(
        tmp_path / "slas.yaml",
        catalog(rule(target=target)),  # type: ignore[arg-type]
    )
    with pytest.raises(SlaConfigError) as excinfo:
        load(path)
    assert excinfo.value.code == "SLA_CONFIG_INVALID"


@pytest.mark.parametrize("target", ["0", "1.01", "-0.5"])
def test_otd_rate_target_range_and_format(tmp_path: Path, target: str) -> None:
    """OTD_RATE accepts only (0, 1]; the negative form is not a decimal string."""
    path = write_catalog(tmp_path / "slas.yaml", catalog(rule(target=target)))
    with pytest.raises(SlaConfigError) as excinfo:
        load(path)
    assert excinfo.value.code == "SLA_CONFIG_INVALID"


@pytest.mark.parametrize(
    ("target", "expects_error"),
    [("3", False), ("0", False), ("3.5", True), ("-1", True), ("many", True)],
)
def test_maximum_metric_targets_must_be_integral_and_non_negative(
    tmp_path: Path, target: str, expects_error: bool
) -> None:
    """The two maximum metrics accept integral non-negative targets only."""
    payload = catalog(rule(metric="MAX_LEAD_TIME_DAYS", target=target))
    if expects_error:
        with pytest.raises(SlaConfigError) as excinfo:
            load(write_catalog(tmp_path / "slas.yaml", payload))
        assert excinfo.value.code == "SLA_CONFIG_INVALID"
    else:
        loaded = load(write_catalog(tmp_path / "slas.yaml", payload))
        assert str(loaded.rules[0].target) == target


def test_inverted_effective_window_is_rejected(tmp_path: Path) -> None:
    """effective_to may equal but never precede effective_from."""
    path = write_catalog(
        tmp_path / "slas.yaml",
        catalog(rule(effective_from="2026-06-01", effective_to="2026-05-31")),
    )
    with pytest.raises(SlaConfigError) as excinfo:
        load(path)
    assert excinfo.value.code == "SLA_CONFIG_INVALID"


def test_unknown_or_non_supplier_origin_is_rejected(tmp_path: Path) -> None:
    """Supplier scopes require a known source that owns supplier data."""
    unknown = catalog(rule(scope=supplier_scope(origin_source_id="missing")))
    with pytest.raises(SlaConfigError) as excinfo:
        load(write_catalog(tmp_path / "unknown.yaml", unknown))
    assert excinfo.value.code == "SLA_CONFIG_INVALID"

    non_supplier = catalog(rule())
    with pytest.raises(SlaConfigError) as excinfo:
        load(write_catalog(tmp_path / "non_supplier.yaml", non_supplier), include_supplier=False)
    assert excinfo.value.code == "SLA_CONFIG_INVALID"


def test_category_scopes_must_already_be_uppercase(tmp_path: Path) -> None:
    """Category scopes are not normalized implicitly."""
    path = write_catalog(
        tmp_path / "slas.yaml",
        catalog(rule(scope=category_scope(category="Electronics"))),
    )
    with pytest.raises(SlaConfigError) as excinfo:
        load(path)
    assert excinfo.value.code == "SLA_CONFIG_INVALID"


def test_duplicate_identifiers_are_rejected(tmp_path: Path) -> None:
    """sla_id values must be unique across scopes and metrics."""
    path = write_catalog(
        tmp_path / "slas.yaml",
        catalog(
            rule(sla_id="SLA-1"),
            rule(sla_id="SLA-1", scope=category_scope(), metric="MAX_LEAD_TIME_DAYS"),
        ),
    )
    with pytest.raises(SlaConfigError) as excinfo:
        load(path)
    assert excinfo.value.code == "SLA_CONFIG_INVALID"


def test_same_scope_and_metric_windows_must_not_overlap(tmp_path: Path) -> None:
    """Overlapping effective windows for one scope and metric are rejected."""
    path = write_catalog(
        tmp_path / "slas.yaml",
        catalog(
            rule(
                sla_id="SLA-1",
                effective_from="2026-01-01",
                effective_to="2026-06-30",
            ),
            rule(
                sla_id="SLA-2",
                effective_from="2026-06-30",
                effective_to="2026-12-31",
            ),
        ),
    )
    with pytest.raises(SlaConfigError) as excinfo:
        load(path)
    assert excinfo.value.code == "SLA_CONFIG_INVALID"


def test_open_ended_window_conflicts_with_a_later_rule(tmp_path: Path) -> None:
    """An open-ended rule conflicts with any later rule for the same key."""
    path = write_catalog(
        tmp_path / "slas.yaml",
        catalog(
            rule(sla_id="SLA-1", effective_from="2026-01-01"),
            rule(
                sla_id="SLA-2",
                effective_from="2026-06-01",
                effective_to="2026-12-31",
            ),
        ),
    )
    with pytest.raises(SlaConfigError) as excinfo:
        load(path)
    assert excinfo.value.code == "SLA_CONFIG_INVALID"


def test_identity_hash_is_rule_order_independent_and_changes_with_rules(
    tmp_path: Path,
) -> None:
    """The canonical hash ignores YAML order and tracks effective content."""
    first = rule(sla_id="SLA-1")
    second = rule(
        sla_id="SLA-2",
        scope=category_scope(),
        metric="MAX_LEAD_TIME_DAYS",
        target="7",
    )
    forward = load(write_catalog(tmp_path / "forward.yaml", catalog(first, second)))
    reverse = load(write_catalog(tmp_path / "reverse.yaml", catalog(second, first)))
    changed = load(
        write_catalog(
            tmp_path / "changed.yaml",
            catalog(first, {**second, "target": "8"}),
        )
    )

    assert forward.catalog_hash == reverse.catalog_hash
    assert forward.resolved_version == reverse.resolved_version
    assert changed.catalog_hash != forward.catalog_hash
    assert changed.resolved_version != forward.resolved_version


def test_supplier_rule_precedes_category_rule_and_windows_are_inclusive(
    tmp_path: Path,
) -> None:
    """Supplier wins while active; category applies otherwise; windows include edges."""
    loaded = load(
        write_catalog(
            tmp_path / "slas.yaml",
            catalog(
                rule(
                    sla_id="SLA-CAT",
                    scope=category_scope(),
                    metric="MAX_LEAD_TIME_DAYS",
                    target="7",
                    effective_from="2026-01-01",
                ),
                rule(
                    sla_id="SLA-SUP",
                    metric="MAX_LEAD_TIME_DAYS",
                    target="3",
                    effective_from="2026-02-01",
                    effective_to="2026-03-31",
                ),
            ),
        )
    )

    def resolve(as_of: date) -> str | None:
        selected = loaded.resolve(
            as_of=as_of,
            metric=SlaMetric.MAX_LEAD_TIME_DAYS,
            origin_source_id="erp_master_data",
            supplier_external_id="SUP-1",
            category="ELECTRONICS",
        )
        return selected.sla_id if selected is not None else None

    assert resolve(date(2026, 2, 1)) == "SLA-SUP"
    assert resolve(date(2026, 3, 31)) == "SLA-SUP"
    assert resolve(date(2026, 4, 1)) == "SLA-CAT"
    assert resolve(date(2026, 1, 31)) == "SLA-CAT"
    assert resolve(date(2025, 12, 31)) is None
    assert (
        loaded.resolve(
            as_of=date(2026, 2, 1),
            metric=SlaMetric.MAX_QUOTE_RESPONSE_DAYS,
            origin_source_id="erp_master_data",
            supplier_external_id="SUP-1",
            category="ELECTRONICS",
        )
        is None
    )
