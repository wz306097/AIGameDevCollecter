from pathlib import Path

from click.testing import CliRunner

from survey.cli import main


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_init_creates_branch(tmp_git_repo: Path, monkeypatch):
    monkeypatch.chdir(tmp_git_repo)
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--name", "test-game"])
    assert result.exit_code == 0
    assert "survey branch" in result.output.lower() or "initialized" in result.output.lower()


def test_config_show(tmp_git_repo: Path, monkeypatch):
    monkeypatch.chdir(tmp_git_repo)
    runner = CliRunner()
    runner.invoke(main, ["init", "--name", "test-game"])
    result = runner.invoke(main, ["config", "show"])
    assert result.exit_code == 0


def test_tag_pending_no_sessions(tmp_git_repo: Path, monkeypatch):
    monkeypatch.chdir(tmp_git_repo)
    runner = CliRunner()
    runner.invoke(main, ["init", "--name", "test-game"])
    result = runner.invoke(main, ["tag", "--pending"])
    assert result.exit_code == 0


def test_report_empty(tmp_git_repo: Path, monkeypatch):
    monkeypatch.chdir(tmp_git_repo)
    runner = CliRunner()
    runner.invoke(main, ["init", "--name", "test-game"])
    result = runner.invoke(main, ["report"])
    assert result.exit_code == 0
    assert "Total sessions: 0" in result.output


def test_init_defaults_name_to_folder(tmp_git_repo: Path, monkeypatch):
    monkeypatch.chdir(tmp_git_repo)
    runner = CliRunner()
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0
    assert tmp_git_repo.name in result.output


def test_collect_auto_inits(tmp_git_repo: Path, monkeypatch):
    monkeypatch.chdir(tmp_git_repo)
    runner = CliRunner()
    # No prior `survey init` — collect must self-initialize, not error.
    result = runner.invoke(main, ["collect"])
    assert result.exit_code == 0
    assert "Collected" in result.output


def test_watch_once(tmp_git_repo: Path, monkeypatch):
    monkeypatch.chdir(tmp_git_repo)
    runner = CliRunner()
    result = runner.invoke(main, ["watch", "--once"])
    assert result.exit_code == 0
    assert "[watch]" in result.output


def test_report_auto_inits(tmp_git_repo: Path, monkeypatch):
    monkeypatch.chdir(tmp_git_repo)
    runner = CliRunner()
    result = runner.invoke(main, ["report"])
    assert result.exit_code == 0
    assert "Total sessions: 0" in result.output
