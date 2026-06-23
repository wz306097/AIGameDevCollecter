import json

from survey.models import HarnessEvent, Turn, Session, Outcome, TagInfo, VerificationResult


def test_harness_event_roundtrip():
    event = HarnessEvent(
        event_id="evt_001",
        harness="claude-code",
        session_id="claude-code_2026-06-18_001",
        timestamp="2026-06-18T10:15:32Z",
        event_type="file_write",
        payload={"file_path": "scripts/enemy.gd", "action": "create"},
    )
    data = event.to_dict()
    restored = HarnessEvent.from_dict(data)
    assert restored == event


def test_turn_roundtrip():
    turn = Turn(
        turn=1,
        user_message="Implement enemy patrol",
        assistant_summary="Created enemy_patrol.gd using Timer + state machine.",
        tool_calls=["Write:scripts/enemy_patrol.gd"],
    )
    data = turn.to_dict()
    restored = Turn.from_dict(data)
    assert restored == turn


def test_session_roundtrip():
    session = Session(
        session_id="claude-code_2026-06-18_001",
        harness="claude-code",
        config={"model": "opus", "skills": ["tdd"]},
        prompts=[
            Turn(
                turn=1,
                user_message="Implement patrol",
                assistant_summary="Done.",
                tool_calls=["Write:scripts/patrol.gd"],
            )
        ],
        system_context={"skills": ["tdd"], "model": "opus"},
        changed_files=["scripts/patrol.gd"],
        commits=["abc1234"],
        verification=VerificationResult(l0_pass=True, l1_pass=False, l1_details=["signal 'timeout' target missing"]),
        outcome=Outcome(
            first_pass_success=False,
            rounds_to_resolution=2,
            ai_lines_changed=45,
            human_lines_changed=3,
        ),
        timestamps={"started": "2026-06-18T10:00:00Z", "ended": "2026-06-18T10:32:00Z"},
    )
    json_str = json.dumps(session.to_dict(), ensure_ascii=False)
    restored = Session.from_dict(json.loads(json_str))
    assert restored.session_id == session.session_id
    assert len(restored.prompts) == 1
    assert restored.verification.l0_pass is True
    assert restored.verification.l1_pass is False
    assert restored.outcome.human_intervention_ratio == 3 / (45 + 3)


def test_session_defaults():
    session = Session(
        session_id="test_001",
        harness="claude-code",
    )
    assert session.prompts == []
    assert session.changed_files == []
    assert session.commits == []
    assert session.config == {}
    assert session.system_context == {}
    assert session.verification is None
    assert session.outcome is None
    assert session.tag is None
    assert session.multi_task is False
    assert session.task_group is None


def test_outcome_human_intervention_ratio():
    o = Outcome(first_pass_success=True, rounds_to_resolution=1, ai_lines_changed=100, human_lines_changed=0)
    assert o.human_intervention_ratio == 0.0

    o2 = Outcome(first_pass_success=False, rounds_to_resolution=3, ai_lines_changed=0, human_lines_changed=0)
    assert o2.human_intervention_ratio == 0.0


def test_tag_info_roundtrip():
    tag = TagInfo(
        bad_case_type="A2",
        auto_detected=True,
        suggested_type="A2",
        confidence="high",
        root_cause="Used wrong signal connection method",
        harness_actionable=True,
        actionable_suggestion="Add Godot 4.3 signal docs to CLAUDE.md",
    )
    data = tag.to_dict()
    restored = TagInfo.from_dict(data)
    assert restored == tag
