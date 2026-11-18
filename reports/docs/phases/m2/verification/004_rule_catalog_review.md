# SDD 004 — Business-Owner Rule-Catalog Review

**Feature:** `004-validation-normalization`  
**Catalog version:** `RULESET_VERSION = "1.0.0"` (28 rules)  
**Review date:** 2026-11-18  
**Participants:** Project owner (business owner); implementation agent (presenter)  
**Outcome:** Approved as-is — no rule, stage, severity, or applicability change

---

## 1. Scope and Method

The business owner reviewed the closed rule catalog in
`src/app/modules/sourcing/validation/catalog.py` against SDD 004 §4, M2-D04,
M2-D04.1, and M2-D05. The review covered:

- the three evaluation stages and their ordering: structural → normalization → business;
- each rule's stable code, severity, and entity applicability;
- the status mapping: any `ERROR` → `QUARANTINED`, only `WARNING` → `WARNING`, no findings → `VALID`;
- the business intent of the nine record-local business rules.

The review is a business-contract approval, not a code review. Predicate
correctness, determinism, and positive/negative/boundary coverage are verified
separately by the Stage 4 rule and coverage tests.

**Applicability key:** All = `supplier`, `requisition`, `quote`,
`purchase_order`, `delivery`. Money = `quote`, `purchase_order`.
Date order = `requisition`, `purchase_order`. Delivery = `delivery`.

---

## 2. Rules Reviewed

| # | Code | Stage | Severity | Applies to | Business rule | Decision |
|---|---|---|---|---|---|---|
| 1 | `STRUCT_REQUIRED_FIELD` | Structural | ERROR | All | A declared required field is absent, null, or blank | Approved |
| 2 | `STRUCT_INVALID_TYPE` | Structural | ERROR | All | A value does not have the declared scalar shape | Approved |
| 3 | `STRUCT_MAX_LENGTH` | Structural | ERROR | All | A string exceeds the declared maximum length | Approved |
| 4 | `STRUCT_INVALID_FORMAT` | Structural | ERROR | All | A value does not match the declared pattern | Approved |
| 5 | `STRUCT_UNKNOWN_ENUM` | Structural | ERROR | All (enum fields) | An enum value is not a key in the declared mapping | Approved |
| 6 | `NORM_DATE_AMBIGUOUS` | Normalization | ERROR | All | A date matches more than one interpretation | Approved |
| 7 | `NORM_DATE_INVALID` | Normalization | ERROR | All | A value cannot be parsed as a date-only value | Approved |
| 8 | `NORM_TIMESTAMP_NO_TIMEZONE` | Normalization | ERROR | All | A naive timestamp has no declared source timezone | Approved |
| 9 | `NORM_TIMESTAMP_AMBIGUOUS` | Normalization | ERROR | All | A local time is ambiguous or nonexistent in the declared zone | Approved |
| 10 | `NORM_TIMESTAMP_INVALID` | Normalization | ERROR | All | A value cannot be parsed as a timestamp | Approved |
| 11 | `NORM_MONEY_INVALID` | Normalization | ERROR | All | A value cannot be parsed as a decimal amount | Approved |
| 12 | `NORM_MONEY_AMBIGUOUS_SEPARATOR` | Normalization | ERROR | All | Separators are ambiguous under the declared convention | Approved |
| 13 | `NORM_MONEY_PRECISION` | Normalization | ERROR | All | An amount has more than four decimal places | Approved |
| 14 | `NORM_MONEY_RANGE` | Normalization | ERROR | All | An amount is outside the supported numeric range | Approved |
| 15 | `NORM_CURRENCY_INVALID` | Normalization | ERROR | All | A currency is not a supported ISO 4217 code | Approved |
| 16 | `NORM_CURRENCY_MISMATCH` | Normalization | ERROR | All | A record declares more than one currency | Approved |
| 17 | `NORM_QUANTITY_INVALID` | Normalization | ERROR | All | A value cannot be parsed as a decimal quantity | Approved |
| 18 | `NORM_QUANTITY_PRECISION` | Normalization | ERROR | All | A quantity has more than four decimal places | Approved |
| 19 | `NORM_QUANTITY_RANGE` | Normalization | ERROR | All | A quantity is outside the supported numeric range | Approved |
| 20 | `BUSINESS_MISSING_IDENTITY` | Business | ERROR | All | No external identifier and no business identifier are present | Approved |
| 21 | `BUSINESS_DATE_ORDER` | Business | ERROR | Date order | A required date precedes its ordering anchor | Approved |
| 22 | `BUSINESS_AMOUNT_NEGATIVE` | Business | ERROR | Money | An amount is negative | Approved |
| 23 | `BUSINESS_CURRENCY_MISSING` | Business | ERROR | Money | An amount is present without a currency | Approved |
| 24 | `BUSINESS_AMOUNT_ZERO` | Business | WARNING | Money | An amount is zero | Approved |
| 25 | `BUSINESS_CURRENCY_WITHOUT_AMOUNT` | Business | WARNING | Money | A currency is present without an amount | Approved |
| 26 | `BUSINESS_QUANTITY_NON_POSITIVE` | Business | ERROR | Delivery | A delivery quantity is zero or negative | Approved |
| 27 | `BUSINESS_UNIT_MISSING` | Business | WARNING | Delivery | A quantity is present without a unit | Approved |
| 28 | `BUSINESS_SOURCE_TIMESTAMP_MISSING` | Business | WARNING | All | A required source timestamp was not captured | Approved |

---

## 3. Decisions and Conditions

1. All 28 rules, their stages, severities, and applicability are approved as
   recorded. `RULESET_VERSION` remains `1.0.0`.
2. The owner accepted the three `WARNING` rules (24, 25, 27) and rule 28 as
   non-blocking: they retain the normalized payload and never quarantine.
3. The owner accepted that structural and normalization `ERROR` findings
   discard the normalized payload, while business `ERROR` findings retain it
   because normalization completed.
4. The owner accepted `NORM_CURRENCY_MISMATCH` as a catalogued safeguard even
   though the current five canonical entities declare at most one currency
   field; Stage 4 covers it with a direct predicate test (S4-F1).
5. Any later change to a code, stage, severity, applicability, or predicate
   requires a `RULESET_VERSION` increment and a new recorded review (SDD 004
   §4.3). Silent edits are not permitted.

**Recorded outcome:** the catalog is approved for M2 execution. No follow-up
catalog work is required before Stage 5 closes.
