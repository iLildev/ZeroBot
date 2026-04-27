# Arcana — single base image used by every service.
# Build:  docker build -t arcana:latest .
# Run:    docker compose up   (preferred — see docker-compose.yml)

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# System deps:
#   * build-essential / libpq for asyncpg + psycopg fallbacks
#   * git for any "pip install git+…" tools an agent might run
#   * tini for proper PID-1 signal handling
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        build-essential \
        libpq-dev \
        git \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the package + its dependencies once. We copy only the metadata
# first so this layer is cached when source changes but pyproject does not.
COPY pyproject.toml README.md ./
COPY arcana ./arcana
RUN pip install --upgrade pip && pip install -e .

# Per-bot venvs and Builder Agent workspaces are written here at runtime.
RUN mkdir -p /app/runtime_envs

# Default: gateway. Override in docker-compose.yml for the other services.
ENV PORT=8001
EXPOSE 8001

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "arcana.core.gateway:app", "--host", "0.0.0.0", "--port", "8001"]
