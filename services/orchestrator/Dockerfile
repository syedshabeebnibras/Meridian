# Meridian orchestrator service image.
#
# Multi-stage build:
#   1. `builder` — uv sync with only orchestrator deps from the workspace
#   2. `runtime` — slim image with the resolved venv + app code
#
# Build from the repo root:
#   docker build -t meridian-orchestrator:latest -f services/orchestrator/Dockerfile .

FROM python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY --from=ghcr.io/astral-sh/uv:0.10.12 /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy workspace definitions first so uv can resolve without the full source
COPY pyproject.toml uv.lock /app/
COPY packages/ /app/packages/
COPY services/ /app/services/

RUN uv sync --frozen --no-dev --package meridian-orchestrator


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    MERIDIAN_ENV=staging

WORKDIR /app

# Non-root user for the container surface
RUN groupadd --system meridian && useradd --system --gid meridian meridian

COPY --from=builder /app /app

COPY prompts/ /app/prompts/

USER meridian

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz', timeout=2)"

CMD ["uvicorn", "meridian_orchestrator.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
