from pathlib import Path

from survey.branch import BranchStore
from survey.models import Session, Turn


def test_init_branch_creates_orphan(tmp_git_repo: Path):
    store = BranchStore(tmp_git_repo)
    assert not store.branch_exists()
    store.init_branch()
    assert store.branch_exists()


def test_init_branch_idempotent(tmp_git_repo: Path):
    store = BranchStore(tmp_git_repo)
    store.init_branch()
    store.init_branch()
    assert store.branch_exists()


def test_write_and_read_config(tmp_git_repo: Path):
    store = BranchStore(tmp_git_repo)
    store.init_branch()
    config = {"project": {"name": "test-game", "engine": "godot", "engine_version": "4.3"}}
    store.write_config(config)
    loaded = store.read_config()
    assert loaded["project"]["name"] == "test-game"


def test_write_and_read_session(tmp_git_repo: Path):
    store = BranchStore(tmp_git_repo)
    store.init_branch()
    session = Session(
        session_id="claude-code_2026-06-18_001",
        harness="claude-code",
        prompts=[Turn(turn=1, user_message="test", assistant_summary="done", tool_calls=[])],
        changed_files=["scripts/test.gd"],
        timestamps={"started": "2026-06-18T10:00:00Z", "ended": "2026-06-18T10:30:00Z"},
    )
    store.write_session(session)
    loaded = store.read_session("claude-code_2026-06-18_001")
    assert loaded.session_id == session.session_id
    assert loaded.prompts[0].user_message == "test"


def test_list_sessions(tmp_git_repo: Path):
    store = BranchStore(tmp_git_repo)
    store.init_branch()
    for i in range(3):
        session = Session(
            session_id=f"claude-code_2026-06-18_{i:03d}",
            harness="claude-code",
            timestamps={"started": f"2026-06-18T{10+i}:00:00Z", "ended": f"2026-06-18T{10+i}:30:00Z"},
        )
        store.write_session(session)
    sessions = store.list_sessions()
    assert len(sessions) == 3
