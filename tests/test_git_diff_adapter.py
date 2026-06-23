import subprocess
from pathlib import Path

from survey.adapters.git_diff import GitDiffAdapter


def _make_commit(repo: Path, filename: str, content: str, message: str):
    (repo / filename).parent.mkdir(parents=True, exist_ok=True)
    (repo / filename).write_text(content)
    subprocess.run(["git", "add", filename], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)


def test_infer_sessions_single_commit(tmp_git_repo: Path):
    _make_commit(tmp_git_repo, "scripts/player.gd", "extends Node2D\n", "add player")
    adapter = GitDiffAdapter()
    sessions = adapter.infer_sessions(tmp_git_repo, since="1 hour ago", until="now")
    assert len(sessions) >= 1
    assert "scripts/player.gd" in sessions[-1].changed_files


def test_infer_sessions_groups_close_commits(tmp_git_repo: Path):
    _make_commit(tmp_git_repo, "scripts/a.gd", "extends Node\n", "add a")
    _make_commit(tmp_git_repo, "scripts/b.gd", "extends Node\n", "add b")
    adapter = GitDiffAdapter()
    sessions = adapter.infer_sessions(tmp_git_repo, since="1 hour ago", until="now", gap_minutes=60)
    assert len(sessions) == 1
    assert "scripts/a.gd" in sessions[0].changed_files
    assert "scripts/b.gd" in sessions[0].changed_files


def test_infer_sessions_sets_harness_fallback(tmp_git_repo: Path):
    _make_commit(tmp_git_repo, "scripts/c.gd", "extends Node\n", "add c")
    adapter = GitDiffAdapter()
    sessions = adapter.infer_sessions(tmp_git_repo, since="1 hour ago", until="now")
    assert sessions[-1].harness == "unknown"
