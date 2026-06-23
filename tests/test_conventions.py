from pathlib import Path

from survey.validation.conventions import check_conventions


def test_detects_camelcase_script(tmp_path: Path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "enemyPatrol.gd").write_text("extends Node\n")
    rules = {"script_naming": "snake_case", "banned_patterns": []}
    issues = check_conventions(tmp_path, ["scripts/enemyPatrol.gd"], rules)
    assert any("enemyPatrol" in i for i in issues)


def test_accepts_snake_case_script(tmp_path: Path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "enemy_patrol.gd").write_text("extends Node\n")
    rules = {"script_naming": "snake_case", "banned_patterns": []}
    issues = check_conventions(tmp_path, ["scripts/enemy_patrol.gd"], rules)
    assert len(issues) == 0


def test_detects_banned_pattern(tmp_path: Path):
    (tmp_path / "test.gd").write_text('var node = get_node("../../Player")\n')
    rules = {"script_naming": "snake_case", "banned_patterns": ['get_node("../../']}
    issues = check_conventions(tmp_path, ["test.gd"], rules)
    assert any("banned pattern" in i.lower() for i in issues)


def test_no_files_no_issues(tmp_path: Path):
    rules = {"script_naming": "snake_case", "banned_patterns": []}
    issues = check_conventions(tmp_path, [], rules)
    assert issues == []
