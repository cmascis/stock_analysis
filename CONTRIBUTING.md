# Contributing

## Branching Strategy

- `main` is protected and only accepts changes through pull requests.
- Use short-lived branches with one of these prefixes:
  - `feature/<slug>`
  - `fix/<slug>`
  - `chore/<slug>`
  - `docs/<slug>`
- Rebase or merge from `main` frequently to keep your branch current.

## Local Guardrails

This repository is **uv-only**. Use `uv` for dependency and tool management.

1. Install dependencies and hooks:

   ```bash
   ./scripts/bootstrap_dev_guardrails.sh
   ```

2. Run the local CI equivalent before opening a PR:

   ```bash
   ./scripts/run_local_ci.sh
   ```

3. If you want to run push-stage hooks during bootstrap:

   ```bash
   RUN_PUSH_HOOKS=1 ./scripts/bootstrap_dev_guardrails.sh
   ```

## Pull Request Workflow

1. Branch from `main` using the naming convention above.
2. Make focused changes and keep unrelated edits out of scope.
3. Run local checks (`prek`, migration drift, tests).
4. Open a PR against `main` using the PR template checklist.
5. Wait for required checks:
   - `lint`
   - `migrations`
   - `tests`
6. Merge using **Squash and merge** only.

## GitHub Repository Rules

- Merge method: squash merge only.
- Direct pushes to `main`: blocked by branch protection.
- Branch protection requires:
  - pull request workflow
  - required status checks
  - resolved conversations
  - linear history
- Admins are also subject to branch protection.

## Guardrail Automation

Apply GitHub settings with:

```bash
./scripts/apply_github_guardrails.sh --dry-run
./scripts/apply_github_guardrails.sh --apply
```
