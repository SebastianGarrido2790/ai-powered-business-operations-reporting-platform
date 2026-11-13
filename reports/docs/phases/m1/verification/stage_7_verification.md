# M1 — Stage 7: Integrated Acceptance & One-Time Falsification

**Phase:** M1 — Platform Foundation  
**Stage:** 7  
**Verification date:** 2026-11-13  
**Status:** Implementation and verification complete — gate passed and acknowledged by the project owner 2026-11-13
**Gate evidence:** implementation commits `1ee42c3` (S7-F1 remediation); baseline `6be91fe`  
**Authorization:** M1 execution authorized by the project owner on 2026-11-12

---

## 1. Baseline Identity

| Item | Value |
|---|---|
| Branch | `main`, tracking `origin/main` |
| Starting HEAD | `6be91fe` — `docs(M1): Record Stage 6 verification evidence and gate acknowledgement` |
| Working tree at start | Clean |
| Previous stage | Stage 6 passed and acknowledged 2026-11-13 |
| Scope source | `execution_plan.md` Stage 7 and §8 acceptance checklist; SDD 001–005 acceptance criteria |

## 2. Environment

| Item | Value |
|---|---|
| Container runtime | Docker Desktop engine `29.1.3` (daemon started for this stage) |
| Database | `postgres:16-alpine` Compose service, published at `127.0.0.1:5433`, healthy |
| Clean acceptance database | `bopf_stage7` (created empty for this stage) |
| Clean live database | `bopf_stage7_live` (created empty, migrated, used for live checks) |
| API/worker execution | Native `uv run` processes against the containerised PostgreSQL |
| Dependency lock | `uv lock --check` — 136 packages resolved, no lock change |

The Compose API container was not rebuilt; live API and worker checks ran as separate native processes against the same database. This exercises the actual Stage 6 code while preserving the independent-process boundary.

## 3. Integrated Acceptance Results

### 3.1 Clean-database migration

| Check | Evidence | Result |
|---|---|---|
| Empty database upgrades from base | `alembic upgrade head` on `bopf_stage7`: `0001_platform_schema` → `0002_platform_jobs_and_metadata` | Pass |
| Current revision | `alembic current` → `0002_platform_jobs_and_metadata (head)` | Pass |
| Platform tables | `idempotency_keys`, `job_attempts`, `jobs`, `module_registrations` | Pass |
| Schema ownership | Only `platform` exists; no `sourcing` or `analytics_sourcing` schema | Pass |
| No startup migration | Existing `test_application_startup_does_not_run_migrations` | Pass |
| Downgrade/re-upgrade repeatability | `tests/test_database.py::test_alembic_upgrade_produces_expected_schema_state` executed against PostgreSQL | Pass |

### 3.2 Live API and registry

| Check | Result |
|---|---|
| `GET /health` (public liveness) | 200 — process liveness, no dependency evaluation |
| `GET /api/v1/platform/health` unauthenticated | 401 `unauthenticated`, correlation ID present in the error envelope and `X-Correlation-ID` header |
| `GET /api/v1/platform/health` authenticated | 200 — `status=ok`, `database=connected` |
| `GET /api/v1/platform/readiness` authenticated | 200 — `status=ready`, `database=connected`, `module_registry=ready` |
| `GET /api/v1/platform/modules` | 200 — Sourcing `0.1.0`, `registered`, capability `health` |
| `GET /api/v1/platform/modules/sourcing/health` | 200 — `status=ok`, `reason=null` |

### 3.3 End-to-end job execution and correlation

| Check | Evidence | Result |
|---|---|---|
| Submission returns immediately | `POST /api/v1/platform/jobs` → 201, `status=QUEUED`, attempts 0 | Pass |
| No synchronous execution | Job executed only by the independent worker process | Pass |
| Worker claims and completes | `job_claimed` attempt 1 → `job_succeeded`; API reports `SUCCEEDED` | Pass |
| Correlation continuity | Request header `stage7-e2e-7327047e…` = persisted `correlation_id` = API `job_submitted` log = worker `job_claimed`/`job_succeeded` logs | Pass |
| Structured API log | `request_completed` JSON event with method, path, status, duration, correlation, `service=api` | Pass |
| Structured worker log | Same schema with `service=worker` | Pass |
| Idempotent resubmission | Same idempotency key → 201 with the **same** `job_id`; exactly one job row for the key | Pass |
| No credential leakage | Log scan for `Bearer`, subject, and JWT material found nothing | Pass |

### 3.4 Health behavior under dependency failure

`docker compose stop db` was used to remove PostgreSQL while the API remained running.

| Check | Result |
|---|---|
| Liveness during outage | 200 in 0.01 s, while a readiness probe was in flight |
| Platform health during outage | 503 in 3.01 s — `status=degraded`, `database=unreachable` |
| Readiness during outage | 503 in 3.05 s — `status=not_ready`, `database=unreachable` |
| Recovery after `docker compose start db` | Liveness, platform health, and readiness all 200 again |

## 4. One-Time Falsification: Worker Interruption During Execution

**Hypothesis:** an interruption after claim but before completion must not lose the job or leave it unobservable, and recovery must not create duplicate effects.

**Controlled procedure executed**

1. Submitted one `test.echo` job through the API with a unique correlation ID and idempotency key (`b3631709-43fe-4164-8884-14d3894b5bac`).
2. A controlled claim process claimed the job with a 3-second lease (accelerated from the production 5-minute lease; the recovery policy is unchanged) and then blocked, simulating a worker crash after claim.
3. The claim process tree was force-terminated (`taskkill /T /F`) before completion.
4. Observed persisted state: `RUNNING`, attempt 1 open, correlation intact, one job row for the idempotency key.
5. Waited for the lease to expire and started the production worker with `--once` (`sweep=True`).
6. Observed recovery and execution; re-read persisted state and API state.

**Evidence**

| Observation | Result |
|---|---|
| Post-interruption state | `RUNNING`, `attempt_count=1`, attempt 1 `RUNNING` (no silent loss) |
| Recovery | Worker log `jobs_recovered` → `RETRY_SCHEDULED` for the job |
| Retry execution | `job_claimed` attempt 2 → `job_succeeded` |
| Terminal state | `SUCCEEDED`, `attempt_count=2` |
| Attempt history | 1 `FAILED` — “Claim lease expired before completion; job recovered.”; 2 `SUCCEEDED` |
| Correlation continuity | Same `stage7-falsify-4fbbb436…` in request, persisted record, and recovery/retry logs |
| Duplicate effects | Resubmission with the same idempotency key returned the same `job_id`; exactly one job row |
| Post-falsification suite | 203 passed, 0 skipped |

A failed falsification would have failed the stage gate; it passed.

## 5. Quality Gates

| Check | Command | Result |
|---|---|---|
| Formatting | `uv run --frozen ruff format --check .` | Pass — 128 files already formatted |
| Linting | `uv run --frozen ruff check .` | Pass — no findings |
| Static typing | `uv run --frozen mypy src tests` | Pass — 77 source files, strict mode, zero errors |
| Full suite with PostgreSQL | `BOPF_TEST_DATABASE_URL=…bopf_stage7 pytest -q` | **203 passed, 0 skipped**, 96% coverage |
| Post-falsification suite | Same command after the interruption experiment | **203 passed, 0 skipped** |

All 21 tests that previously skipped without `BOPF_TEST_DATABASE_URL` now execute and pass.

## 6. Findings

| ID | Finding | Severity | Status |
|---|---|---|---|
| S7-F1 | With PostgreSQL stopped, `/api/v1/platform/readiness` and `/api/v1/platform/health` hung beyond 90 seconds. Two causes: the engine had no bounded connect timeout, so a black-holed connection attempt waited on the OS timeout; and the synchronous probe ran on the event loop, so liveness could be delayed behind it. **Remediation:** `create_engine_from_settings` now sets a 3-second `connect_timeout`, and both health handlers run the database probe via `run_in_threadpool`. Verified: 503 in ~3 s, liveness 200 in 0.01 s during the probe, recovery to 200 after restart. Regression test: `tests/test_database.py::test_engine_sets_bounded_connect_timeout`. | High | Resolved within Stage 7 — evidence above |
| S7-F2 | The Compose API image was not rebuilt; live acceptance used native API/worker processes against the containerised database. Container image build and Compose-level log inspection remain unverified locally. | Low | Accepted — independent-process behavior and the actual application code were exercised; image build is unchanged from Stage 6 |
| S7-F3 | CI has not yet run on the Stage 7 commits because they are not pushed. The same gates passed locally with PostgreSQL. | Low | Pending — verify CI green after the authorized push |
| S7-F4 | A native PostgreSQL instance unrelated to the project listens on 5432 and rejected the compose credentials; the Compose service on 5433 was used exclusively. | Info | No impact on evidence |

No unresolved critical or high-severity finding remains. The S7-F1 remediation is the only production-code change in this stage.

## 7. Changes Introduced

| File | Change |
|---|---|
| `src/app/core/database.py` | Added `DB_CONNECT_TIMEOUT_SECONDS = 3` and passed it as `connect_args` so connection attempts are bounded. |
| `src/app/api/v1/platform/health.py` | Database probes in `/health` and `/readiness` run in a threadpool, keeping the event loop and liveness responsive. |
| `tests/test_database.py` | Added regression coverage for the bounded connect timeout. |

No contract, dependency, or schema change was introduced.

## 8. Not Performed

- Rebuilding and running the Compose API/worker images (the image predates Stages 6–7).
- CI execution on the Stage 7 commit (requires the authorized push).
- Production-scale load, external log aggregation, metrics, and distributed tracing — outside M1 scope.
- Sourcing business workflows — out of M1 scope.

## 9. Stage 8 Handoff

Stage 7 satisfies its hard gate: the full suite passes with a live PostgreSQL database, clean-database migrations are verified, API and worker run independently, submission → execution → persistence → status works end to end, correlation is continuous, health semantics behave correctly under dependency failure, and the controlled interruption experiment passed without duplicate effects. Stage 8 (ADR Consolidation & Phase Sign-Off) can reconcile decisions against this evidence, complete the Post-Implementation Review, resolve or accept remaining findings, and obtain M1 sign-off.
