#!/usr/bin/env bash
set -euo pipefail

mode="${1:-push}"
branch="$(git rev-parse --abbrev-ref HEAD)"

# CI jobs commonly run in detached HEAD. Branch policy for CI is enforced
# by the Branch Policy workflow, so local commit/push hooks should no-op here.
if [[ "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "true" ]]; then
  exit 0
fi

case "${mode}" in
  commit)
    if [[ "${ALLOW_MAIN_COMMIT:-0}" == "1" ]]; then
      echo "Branch policy bypass enabled via ALLOW_MAIN_COMMIT=1."
      exit 0
    fi
    ;;
  push)
    if [[ "${ALLOW_MAIN_PUSH:-0}" == "1" ]]; then
      echo "Branch policy bypass enabled via ALLOW_MAIN_PUSH=1."
      exit 0
    fi
    ;;
  *)
    echo "ERROR: Unknown mode '${mode}'. Use 'commit' or 'push'."
    exit 1
    ;;
esac

if [[ "${branch}" == "HEAD" ]]; then
  echo "ERROR: Detached HEAD is not allowed for ${mode} operations."
  echo "Create or switch to a named topic branch first."
  exit 1
fi

if [[ "${branch}" =~ ^(main|master)$ ]]; then
  if [[ "${mode}" == "commit" ]]; then
    echo "ERROR: Direct commits to ${branch} are blocked by local policy."
    echo "Create a topic branch and open a PR to main."
    echo "Emergency override: ALLOW_MAIN_COMMIT=1 git commit ..."
    exit 1
  fi

  echo "ERROR: Direct pushes to ${branch} are blocked by local policy."
  echo "Create a topic branch and open a PR to main."
  echo "Emergency override: ALLOW_MAIN_PUSH=1 git push"
  exit 1
fi

if [[ "${branch}" =~ ^dependabot/ ]]; then
  exit 0
fi

if [[ ! "${branch}" =~ ^(feature|fix|chore|docs|refactor|test|hotfix|release)/[a-z0-9._-]+$ ]]; then
  echo "ERROR: Branch '${branch}' does not match policy."
  echo "Use: <type>/<short-description>"
  echo "Allowed types: feature, fix, chore, docs, refactor, test, hotfix, release"
  exit 1
fi
