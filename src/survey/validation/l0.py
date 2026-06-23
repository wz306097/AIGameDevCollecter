from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


def check_gd_syntax(project_root: Path, gd_files: list[str]) -> list[str]:
    issues = []
    for gd_rel in gd_files:
        gd_path = project_root / gd_rel
        if not gd_path.exists():
            issues.append(f"{gd_rel}: file not found")
            continue
        content = gd_path.read_text(encoding="utf-8", errors="replace")
        paren_depth = 0
        for i, char in enumerate(content):
            if char == "(":
                paren_depth += 1
            elif char == ")":
                paren_depth -= 1
            if paren_depth < 0:
                issues.append(f"{gd_rel}: unmatched ')' near character {i}")
                break
        if paren_depth > 0:
            issues.append(f"{gd_rel}: unclosed '(' ({paren_depth} remaining)")

        func_no_colon = re.compile(r"^func\s+\w+\s*\([^)]*\)\s*$", re.MULTILINE)
        for match in func_no_colon.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            issues.append(f"{gd_rel}:{line_num}: function definition missing ':'")

    return issues


def run_l0(
    project_root: Path,
    scenes: list[str],
    godot_binary: str = "godot",
) -> tuple[bool, list[str]]:
    issues: list[str] = []

    gd_files = [
        str(p.relative_to(project_root))
        for p in project_root.rglob("*.gd")
    ]
    issues.extend(check_gd_syntax(project_root, gd_files))

    if shutil.which(godot_binary):
        for scene in scenes:
            try:
                result = subprocess.run(
                    [godot_binary, "--headless", "--path", str(project_root), scene, "--quit-after", "2"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    issues.append(f"L0 crash: {scene} exited with code {result.returncode}")
                stderr = result.stderr or ""
                for line in stderr.splitlines():
                    if "ERROR" in line:
                        issues.append(f"L0 crash: {scene}: {line.strip()}")
            except subprocess.TimeoutExpired:
                issues.append(f"L0 crash: {scene} timed out after 10s")
            except FileNotFoundError:
                issues.append(f"L0 crash: godot binary '{godot_binary}' not found")
                break

    return len(issues) == 0, issues
