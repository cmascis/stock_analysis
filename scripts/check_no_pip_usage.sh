#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

SEARCH_PATHS=(
  ".github"
  "scripts"
  ".pre-commit-config.yaml"
  "pyproject.toml"
)

if rg -n \
  --glob '!scripts/check_no_pip_usage.sh' \
  -e 'python -m pip' \
  -e '(^|[[:space:]])pip3?[[:space:]]+install([[:space:]]|$)' \
  -e 'package-ecosystem:[[:space:]]*"pip"' \
  "${SEARCH_PATHS[@]}"; then
  echo
  echo "Forbidden pip usage detected. This is a uv-only project."
  echo "Use uv commands instead (for example: uv sync, uv add, uv run, uv tool)."
  exit 1
fi

echo "No forbidden pip usage found."
