# Documentation Policy

Canonical rules for keeping documentation current for developers and agents.

## Core requirement

For every investigation or implementation task, persist net-new knowledge before closing the task.

Net-new knowledge includes:

- Decisions and tradeoffs.
- Newly discovered caveats or constraints.
- Newly introduced workflows or guardrails.
- Behavior changes and usage expectations.
- Operational details needed by the next developer or agent.

## Placement rules

- Cross-cutting, always-on operating rules belong in `AGENTS.md`.
- Topic-specific detail belongs in focused docs under `docs/`.
- Branch and PR flow belongs in `docs/branching-strategy.md`.
- Tooling and commands belong in `docs/tooling.md`.

## Update expectations

- Keep docs concise, accurate, and discoverable.
- Prefer updating an existing canonical doc over creating duplicates.
- Add references in `AGENTS.md` when introducing a new canonical doc.
- Avoid stale command variants; prefer `uv run` / `uv tool run`.
- Correct documentation drift discovered during investigations even if no code changes are made.
- If a workflow depends on a local-only artifact that may not exist in the repository, label it clearly as optional or user-supplied.
- Never document secrets, credentials, or personal sensitive data.

## Feature-hygiene policy

For every feature implementation, explicitly review:

- CI workflows (`.github/workflows/`) for new or updated checks.
- Prek hooks/config (`.pre-commit-config.yaml`) for useful local enforcement.
- Automated tests (unit/integration/model tests) for new behavior.
- Run configurations (`.run/`) for frequently executed project workflows.
- Helper scripts (`scripts/`) for repeatable validation or operational tasks.

If no updates are needed in one or more areas, document that determination in PR notes.

## Completion gate

A task is not complete until:

1. Code/config changes are done.
2. Relevant checks have been run.
3. Documentation has been updated for any net-new knowledge introduced.
