from survey.report import generate_bench_report, generate_report
from survey.models import Session, Turn, Outcome, VerificationResult, TagInfo


def _make_session(
    sid: str,
    harness: str,
    config_id: str,
    l0=True,
    l1=True,
    first_pass=True,
    rounds=1,
    ai=20,
    human=0,
    bad_type=None,
    suggested_type=None,
) -> Session:
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
    if bad_type or suggested_type:
        session.tag = TagInfo(
            bad_case_type=bad_type,
            suggested_type=suggested_type,
            auto_detected=True,
            notes="detected",
        )
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


def test_report_counts_auto_detected_pending_bad_cases():
    sessions = [_make_session("s1", "cc", "x", suggested_type="C1")]
    md = generate_report(sessions, "2026-06-18")
    assert "Bad cases: 1" in md
    assert "C1" in md


def test_generate_bench_report_exports_bad_cases_by_default():
    sessions = [
        _make_session("bad", "cc", "x", suggested_type="C1", human=10),
        _make_session("clean", "cc", "x"),
    ]
    sessions[0].system_context["total_tokens"] = 123

    report = generate_bench_report(sessions, harness="survey-godot-demo")

    assert report["harness"] == "survey-godot-demo"
    assert report["count"] == 1
    assert report["mean_score"] == 0.0
    row = report["testcases"][0]
    assert row["testcase_id"] == "bad"
    assert row["category"] == "survey:C1"
    assert row["score"] == 0.0
    assert row["verifier_result"]["status"] == "fail"
    assert row["survey_session"]["bad_case_type"] == "C1"
    assert row["survey_session"]["prompts"][0]["user_message"] == "x"
    assert row["survey_session"]["system_context"]["total_tokens"] == 123


def test_generate_bench_report_can_include_clean_sessions():
    sessions = [
        _make_session("bad", "cc", "x", suggested_type="C1", human=10),
        _make_session("clean", "cc", "x"),
    ]

    report = generate_bench_report(sessions, include_clean=True)

    assert report["count"] == 2
    by_id = {row["testcase_id"]: row for row in report["testcases"]}
    assert by_id["bad"]["score"] == 0.0
    assert by_id["clean"]["score"] == 1.0
    assert by_id["clean"]["category"] == "survey:clean"


def test_generate_bench_report_attaches_transcript_context_by_commit():
    bad = _make_session("bad", "unknown", "x", suggested_type="C1", human=10)
    bad.prompts = []
    bad.commits = ["abc1234"]
    bad.changed_files = ["scripts/enemy.gd"]

    context = _make_session("codex", "codex", "x")
    context.prompts = [
        Turn(turn=1, user_message="create enemy", assistant_summary="created", tool_calls=[]),
        Turn(turn=2, user_message="fix enemy", assistant_summary="fixed", tool_calls=[]),
    ]
    context.tag = None
    context.commits = ["abc1234"]
    context.system_context = {
        "transcript_format": "codex-jsonl",
        "turn_commits": {"2": ["abc1234"]},
        "codex_session_id": "codex123",
    }

    report = generate_bench_report([bad, context])
    row = report["testcases"][0]

    assert row["testcase_id"] == "bad"
    assert row["survey_session"]["harness"] == "codex"
    assert row["survey_session"]["config"] == bad.config
    assert row["survey_session"]["prompts"][0]["user_message"] == "fix enemy"
    assert row["survey_session"]["system_context"]["codex_session_id"] == "codex123"
    assert row["survey_session"]["system_context"]["transcript_filtered_turns"] == [2]
    assert row["ai_agent_context"]["codex_session_id"] == "codex123"
    assert row["ai_agent_context"]["turns"][0]["agent_input"] == "fix enemy"
    assert row["ai_agent_context"]["turns"][0]["agent_output"] == "fixed"
