from __future__ import annotations

import subprocess
from pathlib import Path


def git_run(args: list[str], cwd: Path | str, input: str | None = None) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        input=input,
    )
    return result.stdout


def get_repo_root(cwd: Path | str) -> Path:
    output = git_run(["rev-parse", "--show-toplevel"], cwd=cwd)
    return Path(output.strip())
