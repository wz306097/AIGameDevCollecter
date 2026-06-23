from pathlib import Path

from survey.config import (
    load_global_config,
    load_repo_config,
    DEFAULT_GLOBAL_CONFIG,
    DEFAULT_REPO_CONFIG,
)


def test_default_global_config_has_required_keys():
    assert "godot" in DEFAULT_GLOBAL_CONFIG
    assert "binary" in DEFAULT_GLOBAL_CONFIG["godot"]
    assert "transcript_sources" in DEFAULT_GLOBAL_CONFIG


def test_load_global_config_returns_defaults_when_missing(tmp_path: Path):
    config = load_global_config(config_dir=tmp_path / "survey")
    assert config["godot"]["binary"] == "godot"


def test_load_global_config_merges_file(tmp_path: Path):
    config_dir = tmp_path / "survey"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text('[godot]\nbinary = "/usr/bin/godot4"\n')
    config = load_global_config(config_dir=config_dir)
    assert config["godot"]["binary"] == "/usr/bin/godot4"
    assert "transcript_sources" in config


def test_load_repo_config_from_fixture():
    fixture = Path(__file__).parent / "fixtures" / "survey.toml"
    config = load_repo_config(fixture)
    assert config["project"]["name"] == "test-game"
    assert len(config["harnesses"]) == 2
    assert config["conventions"]["script_naming"] == "snake_case"


def test_default_repo_config_has_required_keys():
    assert "project" in DEFAULT_REPO_CONFIG
    assert "validation" in DEFAULT_REPO_CONFIG
    assert "conventions" in DEFAULT_REPO_CONFIG
    assert "labels" in DEFAULT_REPO_CONFIG
