# 004 — PostgreSQL & Migration Foundation: Tasks

**Status:** Active — approved for execution under the M0 authorization (2026-11-07); tasks not started  
**Parent:** [`spec.md`](spec.md) · [`plan.md`](plan.md)  
**Phase stage:** M0 Stage 5

## Ordered tasks

- [ ] Confirm schema ownership and migration path against System Design and M0-D04.
- [ ] Add the PostgreSQL driver required by the approved synchronous or asynchronous connection mode.
- [ ] Implement centralized SQLAlchemy engine/connection configuration using validated settings.
- [ ] Configure `alembic.ini` and the migration environment under the approved migration directory.
- [ ] Implement the minimal baseline migration; do not add business or job tables.
- [ ] Verify a database connection against the PostgreSQL service started by Compose.
- [ ] Rebuild the API image with the DB configuration and migration files.
- [ ] Run Alembic upgrade to head on a clean disposable database through the Compose environment.
- [ ] Verify the current revision and expected schema state.
- [ ] Recreate a clean disposable database and repeat the upgrade.
- [ ] Verify no migration executes implicitly during API startup.
- [ ] Document migration commands and safe local reset procedure.

## Completion evidence

- Database connection check result.
- Alembic revision and migration execution output.
- Schema inspection showing only the approved baseline objects.
- Clean re-upgrade result.
- Stage 5 gate recorded as Passed in `execution_plan.md`.
