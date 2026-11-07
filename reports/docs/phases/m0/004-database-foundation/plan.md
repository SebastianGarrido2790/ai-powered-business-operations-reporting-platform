# 004 — PostgreSQL & Migration Foundation: Plan

**Status:** Draft — implementation not authorized  
**Parent:** [`spec.md`](spec.md)  
**Phase stage:** M0 Stage 5

## Approach

1. Confirm the database schema/migration location against the approved System Design and existing `database/migrations/` placeholder.
2. Add the PostgreSQL driver required by the selected SQLAlchemy connection mode. Prefer synchronous SQLAlchemy with psycopg for this minimal M0 foundation unless System Design requires async access.
3. Define one centralized engine/connection configuration using the validated settings from SDD 003.
4. Configure Alembic to use the approved connection settings and migration directory.
5. Establish the minimal baseline migration. Create the already-defined `platform` schema only; no business tables or job metadata are in M0 scope. This is a migration baseline, not implementation of the Platform Runtime persistence model.
6. Keep migration execution explicit through documented commands; never run migrations implicitly from FastAPI startup.
7. Verify connection and migration behavior against a disposable PostgreSQL database.

## Implementation constraints

- Do not introduce ORM models without an M0 requirement.
- Do not create sourcing, analytics, job, or speculative platform tables.
- Do not create a second migration framework or parallel migration history.
- Do not run destructive downgrade operations against shared or persistent data.
- Stage 0 must confirm that no accepted decision defers creation of the already-defined `platform` schema to M1. If such a conflict exists, stop and return it to `implementation_plan.md`; do not silently change the approved migration boundary.

## Validation

- Database connection succeeds from the project environment.
- Alembic upgrade reaches the expected revision.
- Expected schema state is verified in PostgreSQL.
- Clean database upgrade is repeatable.
- Migration command is documented and no startup migration side effect exists.

## Handoff

Stage 5 closes when the migration and connection gates pass. Stage 7 re-verifies the database path from a fresh clone using the documented containerized environment.
