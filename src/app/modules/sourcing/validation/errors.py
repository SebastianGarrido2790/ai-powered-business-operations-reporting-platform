"""Sourcing validation configuration and contract errors.

Governed by:
- SDD 004 §5.3 / §11: configuration failures are permanent and sanitized.
- INV-016: errors carry identifiers and safe messages only; never payloads,
  secrets, credentials, connection strings, or stack traces.
"""


class SourcingValidationConfigError(Exception):
    """The validation configuration is missing, malformed, or inconsistent.

    `code` is a stable diagnostic token safe to expose through module health.
    The message names the source, entity, and field path when available and
    never includes raw values.
    """

    def __init__(self, message: str, *, code: str = "VALIDATION_CONFIG_INVALID") -> None:
        self.code = code
        super().__init__(message)


class SourcingValidationContractError(Exception):
    """A capture result or persisted record violated the validation contract.

    The pipeline raises this when the capture result and persisted records
    disagree; SDD 002 classifies it as a permanent job failure.
    """

    def __init__(self, message: str, *, code: str = "VALIDATION_CONTRACT_VIOLATION") -> None:
        self.code = code
        super().__init__(message)
