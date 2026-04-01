## Summary

Describe what changed and why.

## Validation

- [ ] `uv run prek run --all-files --hook-stage pre-commit`
- [ ] `uv run stock_analysis/manage.py makemigrations --check --dry-run`
- [ ] `uv run stock_analysis/manage.py test stocks investor`

## Checklist

- [ ] Branch follows naming convention (`feature/*`, `fix/*`, `chore/*`, `docs/*`)
- [ ] Scope is focused and unrelated changes are excluded
- [ ] Docs updated when workflow/behavior changes
- [ ] No direct push to `main` (PR-only flow)
