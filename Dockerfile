# ==============================================================================
# BOPF API Dockerfile
#
# Governed by:
# - M0-D02: Python runtime baseline (Python 3.11).
# - M0-D05: Local development container composition.
# - INV-016: Security hygiene; non-root user, no baked secrets.
# ==============================================================================

FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:0.8.11 /uv /bin/uv

# Copy dependency configuration and lockfile first for optimal layer caching
COPY pyproject.toml uv.lock README.md /app/

# Synchronize runtime dependencies in locked mode without installing root project yet
RUN uv sync --locked --no-dev --no-install-project

# Copy application source code
COPY src/ /app/src/

# Install application package itself in locked mode
RUN uv sync --locked --no-dev

# Create non-root system user for security hardening
RUN useradd --create-home --uid 10001 --shell /bin/bash appuser \
    && chown -R appuser:appuser /app

USER appuser

# Expose API port
EXPOSE 8000

# Container liveness check using standard library urllib
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

# Start FastAPI application with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
