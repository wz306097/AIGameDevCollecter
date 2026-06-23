from __future__ import annotations

import re
from pathlib import Path


def _is_snake_case(name: str) -> bool:
    return bool(re.match(r"^[a-z][a-z0-9_]*$", name))


def _is_pascal_case(name: str) -> bool:
    return bool(re.match(r"^[A-Z][a-zA-Z0-9]*$", name))


def check_conventions(
    repo_root: Path,
    changed_files: list[str],
    rules: dict,
) -> list[str]:
    issues: list[str] = []
    script_naming = rules.get("script_naming", "snake_case")
    banned_patterns = rules.get("banned_patterns", [])

    for rel_path in changed_files:
        full_path = repo_root / rel_path
        stem = Path(rel_path).stem

        if rel_path.endswith(".gd") and script_naming == "snake_case":
            if not _is_snake_case(stem):
                issues.append(f"{rel_path}: script name '{stem}' violates snake_case convention")
        elif rel_path.endswith(".tscn") and rules.get("scene_naming") == "PascalCase":
            if not _is_pascal_case(stem):
                issues.append(f"{rel_path}: scene name '{stem}' violates PascalCase convention")

        if banned_patterns and full_path.exists() and rel_path.endswith(".gd"):
            content = full_path.read_text(encoding="utf-8", errors="replace")
            for pattern in banned_patterns:
                if pattern in content:
                    issues.append(f"{rel_path}: contains banned pattern '{pattern}'")

    return issues
