# 001 — Sourcing Connectors

**Phase:** M2 — Data Integration & Processing  
**Status:** Approved — feature specification approved by the project owner 2026-11-14; feature plan and tasks not yet approved; no implementation authorized  
**Parent decision record:** `../implementation_plan.md`  
**Governing decisions:** M2-D01, M2-D01.1  
**Execution stage:** First M2 stage per §7.2; exact stage assignment in the M2 execution plan

## 1. Purpose, context, and expected outcome

**Purpose**

Establish a controlled source-acquisition boundary for Sourcing: a small platform-owned connector contract, Sourcing-owned adapters for the initially supported source types, named source configuration, and a deterministic simulated ERP/CRM interface.

**Context and problem**

M2 must ingest CSV/XLSX files, authorized PostgreSQL data, and REST API data. No connector code exists, and Sourcing currently exposes only health routes. Without a shared acquisition boundary, source-specific behavior would leak into Platform Core or be duplicated across future modules. Allowing callers to supply connection details or filesystem paths would create an unsafe and ungovernable ingestion surface.

**Expected outcome**

External data becomes available to the ingestion application layer through a validated, source-neutral contract. Source access is configuration-driven, secrets stay outside source code and API payloads, files enter through a controlled upload boundary, and the REST path is proven against a deterministic in-repo stub.

## 2. Scope

**Included**

- A platform-owned `DataConnector` contract covering source identity, typed fetch request, source-neutral result envelope, record representation, error classification, execution metadata, timeout, and cancellation.
- Named, versioned, non-secret source configuration loaded and validated at startup.
- Source definitions that declare connector type, non-secret connection parameters, secret-reference names, and authoritative entity types.
- Secret resolution from environment variables only.
- CSV adapter using the standard library with explicit delimiter, encoding, and header handling.
- XLSX adapter using `openpyxl` in read-only mode, without formula evaluation, macros, or external links.
- PostgreSQL adapter using a read-only SQLAlchemy connection, bounded queries, and no writes.
- REST adapter using `httpx` with explicit timeout, pagination, and error classification.
- A multipart file-upload boundary for CSV/XLSX sources with a controlled landing area and acquisition checks.
- An in-repo deterministic simulated ERP/CRM stub with representative supplier, requisition, quote, purchase-order, and delivery payloads.
- Unit and integration tests for the contract, configuration, adapters, upload boundary, and stub.

**Excluded**

- Business validation, normalization, deduplication, reconciliation, and curated persistence. These belong to later M2 SDDs.
- Real ERP/CRM credentials, production system integrations, or external SaaS dependencies.
- Supplier email ingestion (`FR-ING-08`) and ingestion scheduling or freshness monitoring (`FR-ING-09`).
- External object storage, a connector microservice, a plugin framework, or arbitrary dynamic imports.
- Data-quality remediation UI, exception management, KPIs, analytics, or Power BI integration.
- A platform-wide generic ingestion API.
- Changes to the M1 job, security, or module-registration contracts beyond what this feature requires.

## 3. Required behavior

1. When an authorized caller references a named source, the platform shall resolve and validate the source definition before performing any external access.
2. When the source definition is missing, unknown, malformed, or references an unresolved secret, the platform shall reject the request with a classified configuration or authentication error and shall not access the source.
3. When a connector fetches data, it shall return a source-neutral result envelope containing the source identity, fetched records, execution metadata, and any pagination or cursor information.
4. When a source record is returned, it shall carry an external record identifier where the source provides one, the raw payload, the source timestamp where available, and source metadata needed for provenance.
5. When a connector encounters a failure, it shall classify the failure as configuration/authentication, transient, or permanent, and shall not expose secrets or unrestricted payloads in the error.
6. When a connector supports pagination, it shall expose cursor or page metadata and shall respect configured bounds; it shall not loop indefinitely or silently truncate results.
7. When a connector times out or is cancelled, it shall terminate cleanly and shall not present partial data as a complete result.
8. Connectors shall not perform business validation, normalization, deduplication, reconciliation, or curated writes; they shall hand records to the ingestion application layer.
9. The platform shall not accept caller-supplied DSNs, file paths, URLs, or credentials; callers shall reference a `source_id`.
10. When a CSV or XLSX file is submitted, the platform shall generate the stored filename, enforce the allowlisted extension and content type, enforce the maximum file size and row count, and compute a SHA-256 content hash.
11. When a file is encrypted, password-protected, macro-enabled, or otherwise unsupported, the platform shall reject it with an actionable error.
12. The platform shall store uploaded files in a configured, Git-ignored landing directory outside the application package; raw record payloads persisted in PostgreSQL remain the audit source.
13. The REST adapter shall be exercised against an in-repo deterministic stub; no external mock service or real ERP/CRM credential shall be required.
14. Source definitions shall be loaded and validated at startup; an invalid definition shall be rejected and shall not be usable for ingestion.

## 4. Source configuration contract

Source configuration is named, versioned, and non-secret. Each definition shall declare at least:

- `source_id` — a stable identifier referenced by ingestion requests.
- Connector type — one of the supported initial types.
- Non-secret connection parameters required by that connector type.
- Secret-reference names resolved from environment variables.
- Entity types for which the source is authoritative, consumed by reconciliation.

Constraints:

- Secrets shall not appear in committed configuration, API requests, logs, or error responses.
- No dedicated secret store is introduced in M2.
- Duplicate or conflicting `source_id` definitions shall be rejected.
- Configuration is loaded and validated at startup; invalid configuration must be visible and must not silently degrade to a partial source set.
- The exact configuration file format and location are fixed in the feature plan, not in this specification.

## 5. Connector contract boundary

The platform owns the contract; Sourcing owns the adapters.

The contract shall cover:

- Source identity and connector type.
- A typed fetch request and a source-neutral result envelope.
- Records with external identity where available, raw payload, source timestamp, and source metadata.
- Error classification for configuration/authentication, transient, and permanent failures.
- Execution metadata including source, fetched count, duration, and pagination or cursor information.
- Timeout and cancellation behavior owned by the connector implementation.

The contract shall not introduce arbitrary dynamic imports, filesystem discovery, plugin loading, or a connector microservice.

## 6. File acquisition boundary

CSV and XLSX sources are submitted through a multipart upload under the Sourcing ingestion resource.

The platform shall:

- Generate the stored filename; the client filename is metadata only.
- Enforce an allowlisted extension and content type.
- Enforce a maximum file size and a maximum row count.
- Store the file in a configured, Git-ignored landing directory outside the application package.
- Compute a SHA-256 content hash for provenance and duplicate-content detection.
- Reject encrypted, password-protected, macro-enabled, or unsupported workbooks.
- Never accept a caller-supplied server path.

The exact route shape and cleanup policy belong in the API SDD; the exact size and row limits belong in the feature plan. The uploaded file is a transient acquisition artifact; persisted raw record payloads are the audit source.

## 7. Simulated ERP/CRM interface

The REST adapter is exercised against an in-repo deterministic stub.

The stub shall:

- Return representative supplier, requisition, quote, purchase-order, and delivery payloads.
- Be deterministic across runs and suitable for committed fixtures.
- Be clearly identifiable as synthetic; stub payloads must not be presented as production data.
- Support pagination and at least one classified failure mode for testing.
- Require no external service, network dependency, or real credential.

The stub is part of the test and acceptance harness, not a production integration.

## 8. Edge cases

- Missing, unknown, duplicate, or malformed `source_id`.
- Source definition referencing an unresolved or absent secret.
- Empty file; header-only file; file with malformed rows.
- Unsupported extension or content type.
- File exceeding the size or row limit.
- Encrypted, password-protected, macro-enabled, or externally linked workbook.
- CSV with ambiguous delimiter, encoding, or header handling.
- PostgreSQL query exceeding the configured timeout or returning more rows than allowed.
- REST non-2xx response, timeout, rate limit, malformed JSON, or pagination loop.
- Partial fetch caused by a transient failure.
- Cancellation during fetch.
- A source that returns records without an external identifier.

## 9. Error handling

- Errors shall be classified as configuration/authentication, transient, or permanent.
- Error responses and logs shall include the `source_id`, connector type, correlation identifier, and a safe message.
- Secrets, credentials, full connection strings, unrestricted raw payloads, and stack traces shall not be exposed.
- A transient failure shall be distinguishable from a permanent failure so the ingestion execution layer can apply the approved retry policy.
- Partial data shall not be returned or persisted as a complete result.
- Invalid source configuration shall be reported at startup and shall not be silently ignored.

## 10. Non-functional requirements

- **Security:** secrets are resolved from environment variables; no caller-supplied connection details or paths; external content is treated as untrusted data.
- **Reliability:** connector timeouts are explicit; transient failures are distinguishable from permanent failures; partial results are never presented as complete.
- **Performance:** database queries and REST pagination are bounded; file size and row count are limited; no unbounded fetch is permitted.
- **Determinism:** the REST stub and test fixtures produce repeatable results; connector behavior is testable without external services.
- **Synthetic-data distinction:** simulated sources, stub payloads, and fixtures must be clearly identifiable as synthetic and must not be presented as production integrations.
- **Maintainability:** the connector contract is small, typed, and independent of source-specific behavior; adapters are covered by focused tests.
- **Observability:** connector execution metadata and sanitized errors are available for the ingestion run and logs.
- **Compatibility:** the feature does not change the M1 module-registration, job, or security contracts beyond the approved M2 decisions.

## 11. Constraints and governing decisions

- M2-D01 — platform-owned connector contract; Sourcing-owned adapters; named, validated source configuration; secrets from environment variables.
- M2-D01.1 — multipart upload to a controlled landing area; generated filenames; extension, size, and content checks; no caller-supplied paths.
- INV-003 — business modules own domain logic; Platform Core does not own business-specific behavior.
- INV-013 — external content is untrusted and must never redefine policy or approved rules.
- INV-016 — security, least privilege, data access restrictions, and secret management are enforced at execution boundaries.
- INV-017 — no new infrastructure without a concrete requirement.
- ADR-001, ADR-002, ADR-012.
- `openpyxl` becomes a runtime dependency; `pandas` and `pandera` are not introduced.
- `httpx` and `pyyaml` are already available; `python-multipart` is required for the upload boundary and is introduced by the relevant implementation package.
- No connector microservice, plugin marketplace, or arbitrary code loading.

## 12. Acceptance criteria

- [ ] The connector contract is defined and covered by unit tests.
- [ ] A valid named source definition is accepted and resolved.
- [ ] Missing, unknown, duplicate, or malformed source definitions are rejected.
- [ ] An unresolved secret prevents source access and produces a classified error.
- [ ] Secrets do not appear in configuration, API requests, logs, or error responses.
- [ ] The CSV adapter reads valid CSV with explicit delimiter, encoding, and header handling.
- [ ] The XLSX adapter reads valid XLSX in read-only mode and does not evaluate formulas, macros, or external links.
- [ ] The PostgreSQL adapter reads from a seeded read-only source with bounded queries and performs no writes.
- [ ] The REST adapter reads from the deterministic stub, handles pagination, and classifies timeout and non-2xx failures.
- [ ] The multipart upload boundary enforces extension, content type, size, and row limits; generates the stored filename; computes SHA-256; and rejects unsupported workbooks.
- [ ] No caller-supplied DSN, file path, URL, or credential is accepted.
- [ ] The simulated ERP/CRM stub returns deterministic representative payloads and requires no external service.
- [ ] Connectors do not perform business validation, deduplication, reconciliation, or curated writes.
- [ ] Errors are classified and sanitized.
- [ ] Relevant lint, formatting, type-check, and test commands pass.
- [ ] No excluded capability or new infrastructure is introduced.

## 13. Definition of Done

1. This specification is approved by the project owner.
2. The feature plan and tasks are approved.
3. The implementation satisfies every acceptance criterion with observable evidence.
4. Tests cover the contract, configuration validation, each adapter, the upload boundary, the stub, and representative failure modes.
5. No unrelated changes are included.
6. Security, secret handling, and trust boundaries are assessed.
7. Documentation and traceability references are updated.
8. Limitations, skipped checks, and residual risks are reported.

## 14. Dependencies

- M1 platform runtime: module registry, settings, logging, correlation, and security boundaries.
- M2-D01 and M2-D01.1 are approved.
- SDD 002 provides ingestion submission and run lifecycle integration; this feature must not depend on its implementation to define or test the connector contract.
- SDD 003 provides persistence for raw records and provenance; the connector contract must not require it to be complete.
- SDD 006 fixes the external API route shape for file upload; the upload boundary in this feature must remain compatible with that contract.

## 15. Open questions for the feature plan

- Exact source-configuration file format, location, and versioning scheme.
- Exact landing-directory path, cleanup policy, and retention behavior.
- Exact maximum file size, maximum row count, and allowed content types.
- Exact REST stub route shapes, pagination parameters, and failure-injection mechanism.
- How the PostgreSQL adapter represents a missing external record identifier.
- How source-definition validation failures are surfaced at startup without preventing unrelated platform operation.
- Whether connector execution metadata is persisted by the ingestion run or only logged in M2.

## 16. Approval

**Feature scope:** Accepted in the M2 decision record (M2-D01, M2-D01.1).  
**Feature SDD:** Approved — 2026-11-14 by the project owner.  
**Implementation authorization:** Not granted. The feature plan and tasks must be approved, then the M2 execution plan, and explicit execution authorization must be issued before implementation may begin.

