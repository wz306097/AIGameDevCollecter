from pathlib import Path
import subprocess

import pytest

from survey.git_ops import git_run, get_repo_root


def test_git_run_returns_stdout(tmp_git_repo: Path):
    output = git_run(["rev-parse", "--short", "HEAD"], cwd=tmp_git_repo)
    assert len(output.strip()) >= 7


def test_git_run_raises_on_failure(tmp_git_repo: Path):
    with pytest.raises(subprocess.CalledProcessError):
        git_run(["log", "--oneline", "nonexistent-branch"], cwd=tmp_git_repo)


def test_get_repo_root(tmp_git_repo: Path):
    subdir = tmp_git_repo / "a" / "b"
    subdir.mkdir(parents=True)
    root = get_repo_root(subdir)
    assert root == tmp_git_repo
