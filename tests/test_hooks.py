from pathlib import Path

from survey.hooks import generate_post_commit_hook, install_hooks


def test_generate_post_commit_hook_is_valid_shell():
    content = generate_post_commit_hook(Path("/fake/repo"))
    assert content.startswith("#!/")
    assert "survey" in content


def test_install_hooks_creates_file(tmp_git_repo: Path):
    install_hooks(tmp_git_repo)
    hook_path = tmp_git_repo / ".git" / "hooks" / "post-commit"
    assert hook_path.exists()
    content = hook_path.read_text()
    assert "survey" in content
