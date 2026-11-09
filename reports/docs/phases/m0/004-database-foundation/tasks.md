# 004 — PostgreSQL & Migration Foundation: Tasks

**Status:** Completed — Stage 5 implementation and verification complete (2026-11-08)  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** M0 Stage 5

## Ordered tasks

- [x] Confirm schema ownership and migration path against System Design and M0-D04.
- [x] Add the PostgreSQL driver required by the approved synchronous or asynchronous connection mode.
- [x] Implement centralized SQLAlchemy engine/connection configuration using validated settings.
- [x] Configure `alembic.ini` and the migration environment under the approved migration directory.
- [x] Implement the minimal baseline migration; do not add business or job tables.
- [x] Verify a database connection against the PostgreSQL service started by Compose.
- [x] Rebuild the API image with the DB configuration and migration files.
- [x] Run Alembic upgrade to head on a clean disposable database through the Compose environment.
- [x] Verify the current revision and expected schema state.
- [x] Recreate a clean disposable database and repeat the upgrade.
- [x] Verify no migration executes implicitly during API startup.
- [x] Document migration commands and safe local reset procedure.

## Completion evidence

- Database connection check result.
- Alembic revision and migration execution output.
- Schema inspection showing only the approved baseline objects.
- Clean re-upgrade result.
- Stage 5 gate recorded as Passed in `execution_plan.md`.
