from pathlib import Path
from unittest.mock import patch

from survey.validation.l0 import run_l0, check_gd_syntax


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "godot_project"


def test_check_gd_syntax_valid():
    issues = check_gd_syntax(FIXTURE_DIR, ["scripts/main.gd"])
    assert len(issues) == 0


def test_check_gd_syntax_detects_error(tmp_path: Path):
    bad_script = tmp_path / "bad.gd"
    bad_script.write_text("extends Node\n\nfunc _ready(\n  # missing closing paren\n")
    issues = check_gd_syntax(tmp_path, ["bad.gd"])
    assert len(issues) >= 1


def test_run_l0_without_godot_binary():
    passed, details = run_l0(FIXTURE_DIR, ["scenes/main.tscn"], godot_binary="nonexistent_godot_binary")
    assert isinstance(passed, bool)
    assert isinstance(details, list)
