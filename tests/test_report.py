from survey.report import generate_report
from survey.models import Session, Turn, Outcome, VerificationResult, TagInfo


def _make_session(sid: str, harness: str, config_id: str, l0=True, l1=True, first_pass=True, rounds=1, ai=20, human=0, bad_type=None) -> Session:
    session = Session(
        session_id=sid,
        harness=harness,
        config={"id": config_id},
        prompts=[Turn(turn=i+1, user_message="x", assistant_summary="y", tool_calls=[]) for i in range(rounds)],
        verification=VerificationResult(l0_pass=l0, l1_pass=l1),
        outcome=Outcome(
            first_pass_success=first_pass,
            rounds_to_resolution=rounds,
            ai_lines_changed=ai,
            human_lines_changed=human,
            token_cost=1000,
        ),
        timestamps={"started": "2026-06-18T10:00:00Z", "ended": "2026-06-18T10:30:00Z"},
    )
    if bad_type:
        session.tag = TagInfo(bad_case_type=bad_type, auto_detected=True)
    return session


def test_report_contains_summary():
    sessions = [
        _make_session("s1", "claude-code", "opus-base", first_pass=True),
        _make_session("s2", "claude-code", "opus-base", first_pass=False, rounds=3, bad_type="A1"),
    ]
    md = generate_report(sessions, "2026-06-18")
    assert "Total sessions: 2" in md
    assert "Bad cases: 1" in md


def test_report_contains_harness_table():
    sessions = [
        _make_session("s1", "claude-code", "opus-base", first_pass=True),
        _make_session("s2", "claude-code", "opus-tdd", first_pass=True),
        _make_session("s3", "cursor", "cursor-sonnet", first_pass=False, rounds=3),
    ]
    md = generate_report(sessions, "2026-06-18")
    assert "opus-base" in md
    assert "opus-tdd" in md
    assert "cursor-sonnet" in md


def test_report_contains_bad_case_distribution():
    sessions = [
        _make_session("s1", "cc", "x", bad_type="A1"),
        _make_session("s2", "cc", "x", bad_type="A1"),
        _make_session("s3", "cc", "x", bad_type="B3"),
    ]
    md = generate_report(sessions, "2026-06-18")
    assert "A1" in md
    assert "B3" in md


def test_empty_report():
    md = generate_report([], "2026-06-18")
    assert "Total sessions: 0" in md
