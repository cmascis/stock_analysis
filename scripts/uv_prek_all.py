#!/usr/bin/env python3
"""Run full prek checks using uv tooling."""

from __future__ import annotations

import subprocess


def main() -> None:
    subprocess.run(
        ["uv", "tool", "run", "prek", "run", "--all-files", "--show-diff-on-failure"],
        check=True,
    )


if __name__ == "__main__":
    main()
