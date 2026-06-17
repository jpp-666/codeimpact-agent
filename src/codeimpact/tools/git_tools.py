"""Helpers for git and repository inspection."""

from __future__ import annotations

from pathlib import Path
import subprocess


def git_diff(repo: str | Path, ref: str = "HEAD~1..HEAD") -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "diff", ref],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def list_python_files(repo: str | Path) -> list[str]:
    root = Path(repo)
    return [str(path) for path in root.rglob("*.py") if ".git" not in path.parts]
