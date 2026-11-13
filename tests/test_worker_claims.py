"""Concurrent job claim and worker isolation tests (Task 3.4).

Governed by:
- SDD 003 §4: transactional claiming with FOR UPDATE SKIP LOCKED.
- Plan §1.2: concurrent workers must not claim the same job simultaneously.
- INV-008 / INV-009: persistent job status and duplicate-tolerant processing.
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.core.persistence import (
    JobClaim,
    JobStore,
)
from app.core.persistence.job_store import InMemoryJobStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent

requires_database = pytest.mark.skipif(
    not os.environ.get("BOPF_TEST_DATABASE_URL"),
    reason="Database integration tests require BOPF_TEST_DATABASE_URL to be set.",
)


def test_concurrent_claims_do_not_duplicate_job_in_memory() -> None:
    """Verify each queued job is claimed at most once across repeated claim calls.

    The in-memory store is not a concurrency primitive, so claim calls are
    serialized here. This checks claim bookkeeping and ordering; real
    concurrent claim safety is exercised by the PostgreSQL test below.
    """
    store = InMemoryJobStore()
    lock = threading.Lock()

    # Pre-populate 10 jobs
    for i in range(10):
        store.create_job("test.echo", {"index": i})

    claims: list[JobClaim] = []

    def claim_one() -> None:
        with lock:
            c = store.claim_next_job()
        if c is not None:
            claims.append(c)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(claim_one) for _ in range(15)]
        for f in futures:
            f.result()

    # Exactly 10 claims made
    assert len(claims) == 10
    claimed_ids = [c.job_id for c in claims]
    # No duplicate claims
    assert len(set(claimed_ids)) == 10


@requires_database
def test_postgres_concurrent_claims_skip_locked() -> None:
    """Verify FOR UPDATE SKIP LOCKED prevents double-claiming under concurrent sessions."""
    db_url = os.environ["BOPF_TEST_DATABASE_URL"]
    engine = create_engine(db_url)

    try:
        store = JobStore(engine)
        early = datetime.now(UTC) - timedelta(minutes=5)

        # Create 5 jobs
        jobs = [store.create_job("test.echo", {"n": i}, scheduled_at=early) for i in range(5)]

        claims: list[JobClaim] = []
        barrier = threading.Barrier(5)

        def worker_claim_task() -> None:
            local_store = JobStore(engine)
            barrier.wait()  # Synchronize threads to maximize claim contention
            claim = local_store.claim_next_job()
            if claim is not None:
                claims.append(claim)

        threads = [threading.Thread(target=worker_claim_task) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Each thread must claim a unique job
        assert len(claims) == 5
        claimed_ids = {c.job_id for c in claims}
        assert claimed_ids == {j.id for j in jobs}
    finally:
        engine.dispose()
