from __future__ import annotations

import re
from pathlib import Path


def check_script_references(project_root: Path, tscn_files: list[str]) -> list[str]:
    issues = []
    ext_resource_re = re.compile(r'\[ext_resource\s.*?path="res://([^"]+)"')
    for tscn_rel in tscn_files:
        tscn_path = project_root / tscn_rel
        if not tscn_path.exists():
            continue
        content = tscn_path.read_text(encoding="utf-8", errors="replace")
        for match in ext_resource_re.finditer(content):
            ref_path = match.group(1)
            full_path = project_root / ref_path
            if not full_path.exists():
                issues.append(f"{tscn_rel}: missing resource '{ref_path}'")
    return issues


def check_signal_targets(project_root: Path, tscn_files: list[str]) -> list[str]:
    issues = []
    connection_re = re.compile(
        r'\[connection\s+signal="([^"]+)"\s+from="([^"]+)"\s+to="([^"]+)"\s+method="([^"]+)"\]'
    )
    ext_script_re = re.compile(r'\[ext_resource\s.*?type="Script"\s.*?path="res://([^"]+)"')

    for tscn_rel in tscn_files:
        tscn_path = project_root / tscn_rel
        if not tscn_path.exists():
            continue
        content = tscn_path.read_text(encoding="utf-8", errors="replace")

        script_paths = ext_script_re.findall(content)

        defined_methods: set[str] = set()
        for sp in script_paths:
            script_full = project_root / sp
            if script_full.exists():
                script_content = script_full.read_text(encoding="utf-8", errors="replace")
                func_re = re.compile(r"^func\s+(\w+)\s*\(", re.MULTILINE)
                defined_methods.update(func_re.findall(script_content))

        for match in connection_re.finditer(content):
            signal_name = match.group(1)
            method_name = match.group(4)
            if method_name not in defined_methods:
                issues.append(
                    f"{tscn_rel}: signal '{signal_name}' connected to method '{method_name}' which is not defined"
                )
    return issues


def run_l1(project_root: Path, changed_files: list[str]) -> tuple[bool, list[str]]:
    tscn_files = [f for f in changed_files if f.endswith(".tscn")]
    if not tscn_files:
        tscn_files = [
            str(p.relative_to(project_root))
            for p in project_root.rglob("*.tscn")
        ]
    if not tscn_files:
        return True, []

    issues: list[str] = []
    issues.extend(check_script_references(project_root, tscn_files))
    issues.extend(check_signal_targets(project_root, tscn_files))
    return len(issues) == 0, issues
