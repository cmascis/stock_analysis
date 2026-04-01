#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/apply_github_guardrails.sh [--repo owner/name] [--branch main] [--apply]

Defaults to dry-run mode. Pass --apply to execute GitHub changes.
EOF
}

REPO=""
BRANCH="main"
APPLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:-}"
      shift 2
      ;;
    --apply)
      APPLY=1
      shift
      ;;
    --dry-run)
      APPLY=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI is required but was not found in PATH."
  exit 1
fi

if [[ -z "${REPO}" ]]; then
  REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
fi

if [[ -z "${REPO}" ]]; then
  echo "Could not resolve repository. Pass --repo owner/name."
  exit 1
fi

if ! gh auth status -h github.com >/dev/null 2>&1; then
  echo "gh is not authenticated for github.com."
  exit 1
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

REPO_SETTINGS_JSON="${TMP_DIR}/repo-settings.json"
BRANCH_PROTECTION_JSON="${TMP_DIR}/branch-protection.json"

cat > "${REPO_SETTINGS_JSON}" <<'EOF'
{
  "allow_squash_merge": true,
  "allow_merge_commit": false,
  "allow_rebase_merge": false,
  "allow_auto_merge": true,
  "delete_branch_on_merge": true,
  "allow_update_branch": true
}
EOF

cat > "${BRANCH_PROTECTION_JSON}" <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "lint",
      "migrations",
      "tests"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": true
}
EOF

echo "Repository: ${REPO}"
echo "Branch: ${BRANCH}"
if [[ "${APPLY}" -eq 1 ]]; then
  echo "Mode: apply"
else
  echo "Mode: dry-run"
fi

if [[ "${APPLY}" -eq 0 ]]; then
  echo
  echo "[dry-run] Would PATCH repository settings with:"
  cat "${REPO_SETTINGS_JSON}"
  echo
  echo "[dry-run] Would PUT branch protection with:"
  cat "${BRANCH_PROTECTION_JSON}"
  exit 0
fi

gh api \
  -X PATCH \
  "repos/${REPO}" \
  --input "${REPO_SETTINGS_JSON}" \
  >/dev/null

gh api \
  -X PUT \
  "repos/${REPO}/branches/${BRANCH}/protection" \
  --input "${BRANCH_PROTECTION_JSON}" \
  >/dev/null

echo "Applied repository settings and branch protection."
echo "Current protection snapshot:"
gh api \
  "repos/${REPO}/branches/${BRANCH}/protection" \
  --jq '{required_status_checks, enforce_admins, required_pull_request_reviews, required_linear_history, allow_force_pushes, allow_deletions, required_conversation_resolution}'
