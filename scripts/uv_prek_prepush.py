#!/usr/bin/env python3
"""Run prek pre-push stage checks using uv tooling."""

from __future__ import annotations

import subprocess


def main() -> None:
    subprocess.run(
        ["uv", "tool", "run", "prek", "run", "--stage", "pre-push", "--all-files"],
        check=True,
    )


if __name__ == "__main__":
    main()
