"""File acquisition boundary for uploaded CSV and XLSX files.

Governed by:
- INV-013: secure boundary, path traversal prevention, and hash provenance.
- ADR-002: controlled landing area and strict format allowlists.
- M2-D01 / M2-D01.1: streamed upload processing, size limits, and SHA-256 provenance.
- SDD 001 Task 3.1-3.2 / SDD 006: exclude_refs protection for non-terminal runs.
"""

import hashlib
import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Final

from app.core.connectors import (
    ConnectorError,
    ConnectorErrorClass,
)
from app.modules.sourcing.config.settings import SourcingSettings

ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset({".csv", ".xlsx"})

ALLOWED_CONTENT_TYPES: Final[Mapping[str, frozenset[str]]] = {
    ".csv": frozenset({"text/csv", "application/csv"}),
    ".xlsx": frozenset({"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}),
}

CHUNK_SIZE: Final[int] = 64 * 1024  # 64 KiB chunks


@dataclass(frozen=True)
class LandingFileRef:
    """Opaque reference and provenance metadata for an acquired landing file."""

    ref: str
    client_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class FileAcquisitionService:
    """Manages file acquisition, security validation, and landing lifecycle."""

    def __init__(self, settings: SourcingSettings | None = None) -> None:
        self._settings = settings or SourcingSettings()
        self._landing_dir = self._settings.landing_dir.resolve()
        self._validate_landing_dir(self._landing_dir)
        self._landing_dir.mkdir(parents=True, exist_ok=True)

    @property
    def landing_dir(self) -> Path:
        """The resolved directory where landing files are stored."""
        return self._landing_dir

    def _validate_landing_dir(self, directory: Path) -> None:
        """Ensure landing directory is not located within application source package."""
        current = Path(__file__).resolve().parent
        project_root: Path | None = None
        for parent in [current, *current.parents]:
            if (parent / "pyproject.toml").exists():
                project_root = parent
                break
        if project_root is not None:
            src_dir = (project_root / "src").resolve()
            if directory == src_dir or src_dir in directory.parents:
                raise ConnectorError(
                    f"Landing directory cannot be inside application package: {directory}",
                    code="SOURCE_CONFIG_INVALID",
                    error_class=ConnectorErrorClass.CONFIGURATION,
                )

    def resolve_path(self, ref: str) -> Path:
        """Securely resolve an opaque reference to a path within the landing directory."""
        if not ref or ".." in ref or "/" in ref or "\\" in ref:
            raise ConnectorError(
                f"Invalid landing file reference '{ref}'",
                code="SOURCE_CONFIG_INVALID",
                error_class=ConnectorErrorClass.CONFIGURATION,
            )

        resolved = (self._landing_dir / ref).resolve()
        if resolved.parent != self._landing_dir:
            raise ConnectorError(
                f"Path traversal detected in reference '{ref}'",
                code="SOURCE_CONFIG_INVALID",
                error_class=ConnectorErrorClass.CONFIGURATION,
            )
        return resolved

    def acquire(
        self,
        stream: BinaryIO,
        client_filename: str,
        content_type: str,
    ) -> LandingFileRef:
        """Stream and validate an uploaded file into the landing directory.

        Enforces extension and MIME allowlists, limits maximum upload size,
        generates an isolated filename, and computes a SHA-256 digest.
        """
        # Validate client filename extension
        suffix = Path(client_filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
            raise ConnectorError(
                f"Disallowed file extension '{suffix}'. Allowed: {allowed}",
                code="SOURCE_CONFIG_INVALID",
                error_class=ConnectorErrorClass.PERMANENT,
            )

        # Validate MIME content-type
        normalized_mime = content_type.strip().lower().split(";")[0].strip()
        allowed_mimes = ALLOWED_CONTENT_TYPES.get(suffix, frozenset())
        if normalized_mime not in allowed_mimes:
            allowed_str = ", ".join(sorted(allowed_mimes))
            raise ConnectorError(
                f"Content-Type '{content_type}' is not permitted for extension '{suffix}'. "
                f"Allowed: {allowed_str}",
                code="SOURCE_CONFIG_INVALID",
                error_class=ConnectorErrorClass.PERMANENT,
            )

        # Generate isolated landing filename and reference
        stored_filename = f"{uuid.uuid4().hex}{suffix}"
        target_path = self._landing_dir / stored_filename

        hasher = hashlib.sha256()
        total_bytes = 0
        max_bytes = self._settings.max_upload_bytes

        try:
            with target_path.open("wb") as out_file:
                while True:
                    chunk = stream.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise ConnectorError(
                            f"File size exceeds maximum upload limit of {max_bytes} bytes",
                            code="SOURCE_LIMIT_EXCEEDED",
                            error_class=ConnectorErrorClass.PERMANENT,
                        )
                    hasher.update(chunk)
                    out_file.write(chunk)
        except Exception:
            if target_path.exists():
                try:
                    target_path.unlink()
                except OSError:
                    pass
            raise

        return LandingFileRef(
            ref=stored_filename,
            client_filename=client_filename,
            content_type=content_type,
            size_bytes=total_bytes,
            sha256=hasher.hexdigest(),
            created_at=datetime.now(UTC),
        )

    def delete(self, ref: str) -> bool:
        """Delete an acquired file by its reference string. Returns True if deleted."""
        try:
            path = self.resolve_path(ref)
            if path.is_file():
                path.unlink()
                return True
        except (ConnectorError, OSError):
            return False
        return False

    def sweep(
        self,
        older_than_hours: float,
        *,
        exclude_refs: Collection[str] = (),
    ) -> int:
        """Remove landing files older than the specified age, skipping protected refs."""
        if not self._landing_dir.exists():
            return 0

        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        deleted_count = 0
        protected_set = set(exclude_refs)

        for item in self._landing_dir.iterdir():
            if not item.is_file():
                continue
            if item.name in protected_set:
                continue

            try:
                mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=UTC)
                if mtime < cutoff:
                    item.unlink()
                    deleted_count += 1
            except OSError:
                continue

        return deleted_count
