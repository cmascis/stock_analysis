#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but was not found in PATH."
  exit 1
fi

echo "Syncing dependencies (including dev tooling)..."
uv sync --group dev

echo "Installing git hooks with prek..."
uv run prek install --install-hooks --hook-type pre-commit --hook-type pre-push

echo "Running pre-commit stage hooks against all files..."
uv run prek run --all-files --hook-stage pre-commit

if [[ "${RUN_PUSH_HOOKS:-0}" == "1" ]]; then
  echo "RUN_PUSH_HOOKS=1 detected; executing pre-push hooks now..."
  uv run prek run --hook-stage pre-push
else
  echo "Skipping pre-push hooks by default. Set RUN_PUSH_HOOKS=1 to run them now."
fi

echo "Bootstrap complete."
