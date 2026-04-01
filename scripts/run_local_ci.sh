#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but was not found in PATH."
  exit 1
fi

echo "Starting database service..."
docker compose up -d db

echo "Syncing dependencies..."
uv sync --group dev

echo "Running lint and file guardrails..."
uv run prek run --all-files --hook-stage pre-commit

echo "Checking migration drift..."
uv run stock_analysis/manage.py makemigrations --check --dry-run

echo "Applying migrations..."
uv run stock_analysis/manage.py migrate --noinput

echo "Running tests..."
uv run stock_analysis/manage.py test stocks investor

echo "Local CI checks passed."
