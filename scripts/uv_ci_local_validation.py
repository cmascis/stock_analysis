#!/usr/bin/env python3
"""Run local CI-equivalent validation using uv tooling."""

from __future__ import annotations

import os
import subprocess


def run(cmd: list[str], env_overrides: dict[str, str] | None = None) -> None:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    subprocess.run(cmd, check=True, env=env)


def main() -> None:
    run(["docker", "compose", "up", "-d", "db"])
    run(["uv", "sync", "--locked"])
    run(["uv", "run", "python", "stock_analysis/manage.py", "check"])
    run(
        [
            "uv",
            "run",
            "python",
            "stock_analysis/manage.py",
            "makemigrations",
            "--check",
            "--dry-run",
        ]
    )
    run(
        [
            "uv",
            "run",
            "python",
            "stock_analysis/manage.py",
            "test",
            "stocks",
            "investor",
        ]
    )
    run(
        ["uv", "tool", "run", "prek", "run", "--all-files", "--show-diff-on-failure"],
        env_overrides={"CI": "true"},
    )


if __name__ == "__main__":
    main()
