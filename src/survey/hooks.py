from __future__ import annotations

import os
import stat
from pathlib import Path


def generate_post_commit_hook(repo_root: Path) -> str:
    return """#!/bin/sh
# Survey post-commit hook: run L0/L1 checks passively
# Installed by: survey init

if command -v survey >/dev/null 2>&1; then
    survey verify --last --quiet 2>/dev/null &
fi
"""


def install_hooks(repo_root: Path) -> None:
    hooks_dir = repo_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "post-commit"
    content = generate_post_commit_hook(repo_root)

    if hook_path.exists():
        existing = hook_path.read_text()
        if "survey" in existing:
            return
        content = existing.rstrip() + "\n\n" + content

    hook_path.write_text(content)
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC)
