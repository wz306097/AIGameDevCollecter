import subprocess
from pathlib import Path

from survey.metrics import compute_metrics
from survey.models import Session, Turn, VerificationResult


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=cwd, check=True, capture_output=True, text=True)


def _rev_parse(cwd) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_compute_first_pass_success():
    session = Session(
        session_id="s1",
        harness="claude-code",
        prompts=[Turn(turn=1, user_message="do it", assistant_summary="done", tool_calls=["Write:a.gd"])],
        verification=VerificationResult(l0_pass=True, l1_pass=True),
        timestamps={"started": "2026-06-18T10:00:00Z", "ended": "2026-06-18T10:05:00Z"},
    )
    outcome = compute_metrics(session)
    assert outcome.first_pass_success is True
    assert outcome.rounds_to_resolution == 1


def test_compute_multi_round():
    session = Session(
        session_id="s2",
        harness="claude-code",
        prompts=[
            Turn(turn=1, user_message="do it", assistant_summary="done", tool_calls=["Write:a.gd"]),
            Turn(turn=2, user_message="wrong", assistant_summary="fixed", tool_calls=["Edit:a.gd"]),
            Turn(turn=3, user_message="still wrong", assistant_summary="fixed again", tool_calls=["Edit:a.gd"]),
        ],
        verification=VerificationResult(l0_pass=True, l1_pass=True),
        timestamps={"started": "2026-06-18T10:00:00Z", "ended": "2026-06-18T10:30:00Z"},
    )
    outcome = compute_metrics(session)
    assert outcome.first_pass_success is False
    assert outcome.rounds_to_resolution == 3
    assert outcome.session_duration_minutes == 30.0


def test_compute_failed_verification():
    session = Session(
        session_id="s3",
        harness="claude-code",
        prompts=[Turn(turn=1, user_message="x", assistant_summary="y", tool_calls=[])],
        verification=VerificationResult(l0_pass=True, l1_pass=False),
        timestamps={"started": "2026-06-18T10:00:00Z", "ended": "2026-06-18T10:10:00Z"},
    )
    outcome = compute_metrics(session)
    assert outcome.first_pass_success is False


def test_compute_token_cost():
    session = Session(
        session_id="s4",
        harness="claude-code",
        system_context={"total_tokens": 2500},
    )
    outcome = compute_metrics(session)
    assert outcome.token_cost == 2500


def test_line_attribution_splits_ai_and_human(tmp_git_repo: Path):
    repo = tmp_git_repo

    # AI commit: 2 added lines, has a matching Co-Authored-By trailer.
    (repo / "ai.txt").write_text("a\nb\n")
    _git(["add", "ai.txt"], repo)
    _git(["commit", "-m", "ai change\n\nCo-Authored-By: Claude <noreply@anthropic.com>"], repo)
    ai_sha = _rev_parse(repo)

    # Human commit: 1 added line, no trailer.
    (repo / "human.txt").write_text("x\n")
    _git(["add", "human.txt"], repo)
    _git(["commit", "-m", "human change"], repo)
    human_sha = _rev_parse(repo)

    session = Session(session_id="s5", harness="claude-code", commits=[ai_sha, human_sha])
    config = {"global": {"git": {"ai_authors": ["claude", "noreply@anthropic.com"]}}}
    outcome = compute_metrics(session, repo_root=repo, config=config)

    assert outcome.ai_lines_changed == 2
    assert outcome.human_lines_changed == 1
    assert outcome.human_intervention_ratio == 1 / 3


def test_line_attribution_skipped_without_repo_root():
    session = Session(session_id="s6", harness="claude-code", commits=["deadbeef"])
    outcome = compute_metrics(session)
    assert outcome.ai_lines_changed == 0
    assert outcome.human_lines_changed == 0
