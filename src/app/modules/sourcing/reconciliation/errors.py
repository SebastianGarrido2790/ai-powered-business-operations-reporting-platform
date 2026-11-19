"""Sourcing reconciliation contract errors.

Governed by:
- SDD 005 §1.6.1 / §10.1: reconciliation contract violations are permanent
  job failures classified by SDD 002's error mapping.
- INV-016: errors carry identifiers and safe messages only; never payloads,
  secrets, credentials, connection strings, or stack traces.
"""


class SourcingReconciliationContractError(Exception):
    """An input of the reconciliation pipeline violated its contract.

    `code` is a stable diagnostic token safe to expose in logs and run
    summaries. The message names the run, record, and entity involved when
    available and never includes raw values.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "RECONCILIATION_CONTRACT_VIOLATION",
    ) -> None:
        self.code = code
        super().__init__(message)
