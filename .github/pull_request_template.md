## What Changed

-

## Why

-

## Validation

- [ ] Source branch follows policy (`feature/`, `fix/`, `chore/`, `docs/`, `refactor/`, `test/`, `hotfix/`, `release/`, or `dependabot/*`)
- [ ] Feature-hygiene reviewed (CI/workflows, prek hooks/config, tests, run configs, scripts)
- [ ] `uv run python stock_analysis/manage.py check`
- [ ] `uv run python stock_analysis/manage.py makemigrations --check --dry-run`
- [ ] `uv run python stock_analysis/manage.py test stocks investor`
- [ ] `uv tool run prek run --all-files`

## Notes

-
