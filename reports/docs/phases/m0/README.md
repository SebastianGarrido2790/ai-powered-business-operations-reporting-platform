# M0 SDD & Execution Package

**Status:** Draft — no implementation authorized by this package alone.

## Package contents

- `implementation_plan.md` — approved phase decision record (existing canonical document; not replaced by this package).
- `execution_plan.md` — proposed sequential stage workflow and gates.
- `001-project-scaffold/` — project structure and dependency reproducibility SDD.
- `002-application-skeleton/` — minimal application and Sourcing contract SDD.
- `003-local-development-environment/` — configuration, secrets, and API+PostgreSQL Compose SDD.
- `004-database-foundation/` — PostgreSQL and Alembic baseline SDD.

Candidate `005-ci-quality-gates` is intentionally not given a separate SDD. Its approved, limited scope is defined as executable tasks in Stage 6 of `execution_plan.md`.

## SDD details requiring approval

The parent decisions and candidate dispositions are already approved. The feature SDDs still require review of their implementation-level boundaries, particularly:

- **002:** the exact minimal Sourcing contract and the truthful M0 values in the required `manifest.yaml`; no runtime manifest loader or registry is included.
- **003:** reuse of the existing root `Dockerfile` as the single API image definition and reduction of Compose to API + PostgreSQL.
- **004:** synchronous SQLAlchemy/psycopg as the minimal connection mode and a baseline migration that creates only the already-defined `platform` schema, with no tables.
- **005:** Stage 6 includes Ruff, mypy, pytest, and a PostgreSQL test service; the one-time CI falsification is a temporary failing test on a disposable branch.

These are presented as the recommended implementation of the approved decisions, not as permission to expand scope. Any conflict with the canonical System Design or accepted ADRs returns to the phase decision record.

## Approval order

1. Review and approve the four `spec.md` files.
2. Review and approve their corresponding `plan.md` and `tasks.md` files.
3. Review and approve `execution_plan.md`.
4. Authorize Stage 0 explicitly before implementation begins.

Candidate acceptance and approval of M0-D01–D08 do not automatically approve the detailed feature SDDs or authorize implementation.

## Authority

The phase `implementation_plan.md` governs scope and decisions. `execution_plan.md` governs phase sequence and gates. Each feature SDD governs only its feature contract, internal design, and tasks. Root `AGENTS.md`, `invariants.md`, accepted ADRs, and approved requirements remain authoritative.
