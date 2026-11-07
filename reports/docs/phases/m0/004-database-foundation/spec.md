# 004 — PostgreSQL & Migration Foundation

**Phase:** M0 — Project Scaffolding & Engineering Standards  
**Status:** Draft — accepted phase candidate; feature SDD approval pending  
**Parent decision record:** `../implementation_plan.md`  
**Execution stage:** Stage 5; reverified in Stage 7

## 1. Outcome

Establish a working PostgreSQL connection and a minimal, repeatable Alembic migration baseline without implementing Sourcing business persistence or M1 operational tables.

## 2. Need and traceability

- **Roadmap:** M0 — database and migration foundation.
- **PRD:** PF-04.
- **Invariants:** INV-006 and INV-015.
- **Existing ADR:** ADR-003 (PostgreSQL).
- **Parent decision:** M0-D04.

## 3. Current-state evidence

The 2026-11-06 audit at `main@b27375b` found SQLAlchemy and Alembic declared, but no PostgreSQL driver (`psycopg`/`asyncpg`), no `alembic.ini`, no migration environment or versions, and only empty placeholders under `database/`.

## 4. Scope

**In scope**

- PostgreSQL connection using the API+PostgreSQL Compose environment established in Stage 4.
- SQLAlchemy configuration appropriate to the minimal M0 application.
- PostgreSQL driver required by the chosen connection mode.
- Alembic configuration and migration discovery under the existing `database/migrations/` area where compatible with System Design.
- A minimal baseline migration creating the already-defined `platform` schema only; no tables are created in M0.
- Connection and migration verification against a disposable database.
- Documented, explicit migration invocation.

**Out of scope**

- Sourcing business tables, platform metadata tables, job tables, or analytics read models.
- Full application repository pattern, persistence abstraction framework, or async database stack without a concrete need.
- Production migration deployment automation or migrations on API startup.

## 5. Contract and constraints

- PostgreSQL remains the authoritative structured application database.
- Use SQLAlchemy and Alembic as already approved; choose the simplest connection mode sufficient for M0.
- Prefer a synchronous SQLAlchemy/psycopg connection for this minimal foundation unless the approved System Design explicitly requires asynchronous DB access.
- **Recommended baseline:** the initial migration creates the `platform` schema already defined in System Design. It creates no tables; M1 adds platform metadata/job tables and later phases add their domain persistence.
- Schema and table ownership remain explicit; later module migrations must respect module ownership.
- Migrations are version-controlled and explicitly invoked. API startup must not implicitly mutate a production database.
- Migration downgrade/cleanup validation is performed only against a disposable database.

## 6. Acceptance criteria

1. The API/project environment can establish a PostgreSQL connection using validated configuration.
2. Alembic discovers the configured migration environment and revision history.
3. `upgrade head` completes against a clean disposable database.
4. The `platform` schema exists after the baseline migration; no business, job, or speculative platform tables are introduced.
5. Alembic reports the expected current revision.
6. A clean database can repeat the upgrade without manual intervention.
7. Migration commands and the prohibition on implicit production startup migrations are documented.

## 7. Dependencies and handoff

- **Prerequisites:** Stages 1–4 passed; Stage 4 establishes the API+PostgreSQL Compose environment; M0-D04 approved.
- **Downstream:** Stage 7 fresh-clone acceptance re-verifies the database/migration path.
- **Validation:** SQLAlchemy connection check, Alembic upgrade/current, schema inspection, and clean-database re-upgrade.

## 8. Approval

**Feature scope:** Accepted in the M0 decision record.  
**Feature SDD:** Draft; requires human approval before its implementation tasks are activated.
