from survey.inference import detect_multi_task, find_task_group
from survey.models import Session, Turn


def test_single_task_session():
    session = Session(
        session_id="s1",
        harness="claude-code",
        prompts=[
            Turn(turn=1, user_message="...", assistant_summary="...", tool_calls=["Write:scripts/enemy.gd"]),
            Turn(turn=2, user_message="...", assistant_summary="...", tool_calls=["Edit:scripts/enemy.gd"]),
        ],
        changed_files=["scripts/enemy.gd"],
    )
    is_multi, groups = detect_multi_task(session)
    assert not is_multi
    assert len(groups) == 1


def test_multi_task_session():
    session = Session(
        session_id="s2",
        harness="claude-code",
        prompts=[
            Turn(turn=1, user_message="...", assistant_summary="...", tool_calls=["Write:scripts/enemy.gd"]),
            Turn(turn=2, user_message="...", assistant_summary="...", tool_calls=["Edit:scripts/enemy.gd"]),
            Turn(turn=3, user_message="...", assistant_summary="...", tool_calls=["Write:ui/health_bar.gd"]),
            Turn(turn=4, user_message="...", assistant_summary="...", tool_calls=["Write:ui/hud.gd"]),
        ],
        changed_files=["scripts/enemy.gd", "ui/health_bar.gd", "ui/hud.gd"],
    )
    is_multi, groups = detect_multi_task(session)
    assert is_multi
    assert len(groups) == 2


def test_find_task_group_high_overlap():
    new_session = Session(session_id="s3", harness="cc", changed_files=["scripts/enemy.gd", "scenes/enemy.tscn"])
    existing = [
        Session(session_id="s1", harness="cc", changed_files=["scripts/enemy.gd", "scenes/enemy.tscn", "scripts/ai.gd"]),
        Session(session_id="s2", harness="cc", changed_files=["ui/menu.gd"]),
    ]
    group, conf = find_task_group(new_session, existing)
    assert group == "s1"
    assert conf == "high"


def test_find_task_group_no_overlap():
    new_session = Session(session_id="s3", harness="cc", changed_files=["ui/settings.gd"])
    existing = [
        Session(session_id="s1", harness="cc", changed_files=["scripts/enemy.gd"]),
    ]
    group, conf = find_task_group(new_session, existing)
    assert group is None
    assert conf == "none"


def test_find_task_group_uses_commit_overlap():
    new_session = Session(session_id="codex", harness="codex", commits=["abc1234"])
    existing = [
        Session(session_id="unknown_1", harness="unknown", changed_files=["a.gd"], commits=["def5678"]),
        Session(session_id="unknown_2", harness="unknown", changed_files=["b.gd"], commits=["abc1234"]),
    ]
    group, conf = find_task_group(new_session, existing)
    assert group == "unknown_2"
    assert conf == "high"
