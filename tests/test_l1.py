from pathlib import Path

from survey.validation.l1 import run_l1, check_script_references, check_signal_targets


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "godot_project"


def test_check_script_references_finds_missing():
    issues = check_script_references(FIXTURE_DIR, ["scenes/enemy.tscn"])
    missing = [i for i in issues if "missing_texture.png" in i]
    assert len(missing) >= 1


def test_check_script_references_valid_passes():
    issues = check_script_references(FIXTURE_DIR, ["scenes/main.tscn"])
    missing_script = [i for i in issues if "main.gd" in i]
    assert len(missing_script) == 0


def test_check_signal_targets_finds_invalid():
    issues = check_signal_targets(FIXTURE_DIR, ["scenes/enemy.tscn"])
    invalid = [i for i in issues if "nonexistent" in i.lower()]
    assert len(invalid) >= 1


def test_check_signal_targets_valid_passes():
    issues = check_signal_targets(FIXTURE_DIR, ["scenes/enemy.tscn"])
    timeout_issues = [i for i in issues if "timer_timeout" in i.lower()]
    assert len(timeout_issues) == 0


def test_run_l1_returns_tuple(tmp_path: Path):
    passed, details = run_l1(tmp_path, [])
    assert passed is True
    assert details == []


def test_run_l1_on_fixture():
    passed, details = run_l1(FIXTURE_DIR, ["scenes/enemy.tscn"])
    assert passed is False
    assert len(details) >= 2
