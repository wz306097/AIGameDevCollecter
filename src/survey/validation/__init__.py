from __future__ import annotations

from pathlib import Path

from survey.models import VerificationResult
from survey.validation.l0 import run_l0
from survey.validation.l1 import run_l1


def run_validation(
    repo_root: Path,
    changed_files: list[str],
    config: dict,
) -> VerificationResult:
    godot_binary = config.get("global", {}).get("godot", {}).get("binary", "godot")
    scenes = [f for f in changed_files if f.endswith(".tscn")]

    l0_pass, l0_details = run_l0(repo_root, scenes, godot_binary)
    l1_pass, l1_details = run_l1(repo_root, changed_files)

    return VerificationResult(
        l0_pass=l0_pass,
        l1_pass=l1_pass,
        l0_details=l0_details,
        l1_details=l1_details,
    )
