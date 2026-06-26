from pathlib import Path
import json
import subprocess

from click.testing import CliRunner

from survey.cli import main


def subprocess_run(args: list[str], cwd: Path) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


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


def test_export_bench_writes_report(tmp_git_repo: Path, monkeypatch, tmp_path: Path):
    from survey.branch import BranchStore
    from survey.models import Outcome, Session, TagInfo

    monkeypatch.chdir(tmp_git_repo)
    store = BranchStore(tmp_git_repo)
    store.init_branch()
    store.write_session(Session(
        session_id="unknown_2026-06-25_000",
        harness="unknown",
        changed_files=["scripts/player.gd"],
        outcome=Outcome(human_lines_changed=10),
        tag=TagInfo(auto_detected=True, suggested_type="C1", notes="human_intervention_ratio=1.00"),
    ))
    output = tmp_path / "survey_bad_cases.json"

    runner = CliRunner()
    result = runner.invoke(main, [
        "export-bench",
        "--output", str(output),
        "--harness", "survey-godot-demo",
        "--no-transcript",
    ])

    assert result.exit_code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["harness"] == "survey-godot-demo"
    assert data["count"] == 1
    assert data["testcases"][0]["category"] == "survey:C1"


def test_export_bench_writes_testcase_dirs(tmp_git_repo: Path, monkeypatch, tmp_path: Path):
    from survey.branch import BranchStore
    from survey.models import Outcome, Session, TagInfo, Turn

    monkeypatch.chdir(tmp_git_repo)
    store = BranchStore(tmp_git_repo)
    store.init_branch()
    head = subprocess_run(["git", "rev-parse", "HEAD"], tmp_git_repo)
    store.write_session(Session(
        session_id="unknown_2026-06-25_000",
        harness="codex",
        prompts=[Turn(turn=1, user_message="fix timer", assistant_summary="updated timer")],
        changed_files=["README.md"],
        commits=[head[:7]],
        outcome=Outcome(human_lines_changed=10),
        tag=TagInfo(auto_detected=True, suggested_type="C1", notes="human_intervention_ratio=1.00"),
        system_context={"codex_session_id": "codex123", "total_tokens": 123},
    ))
    output = tmp_path / "survey_bad_cases.json"
    testcases_dir = tmp_path / "testcases"

    runner = CliRunner()
    result = runner.invoke(main, [
        "export-bench",
        "--output", str(output),
        "--harness", "survey-godot-demo",
        "--testcases-dir", str(testcases_dir),
        "--no-transcript",
    ])

    assert result.exit_code == 0, result.output
    tc_dir = testcases_dir / "survey-unknown_2026-06-25_000"
    manifest = (tc_dir / "testcase.toml").read_text(encoding="utf-8")
    spec = json.loads((tc_dir / "survey_bad_case.json").read_text(encoding="utf-8"))
    assert 'type = "survey_bad_case"' in manifest
    assert "fix timer" in manifest
    assert spec["bench_record"]["ai_agent_context"]["turns"][0]["agent_input"] == "fix timer"
    assert spec["bench_record"]["ai_agent_context"]["codex_session_id"] == "codex123"


def test_import_transcripts_merges_context_into_bad_case(tmp_git_repo: Path, monkeypatch, tmp_path: Path):
    from survey.branch import BranchStore
    from survey.models import Outcome, Session, TagInfo

    monkeypatch.chdir(tmp_git_repo)
    store = BranchStore(tmp_git_repo)
    store.init_branch()
    store.write_session(Session(
        session_id="unknown_2026-06-25_000",
        harness="unknown",
        changed_files=["scripts/enemy_patrol.gd", "scenes/enemy.tscn"],
        outcome=Outcome(human_lines_changed=10),
        tag=TagInfo(auto_detected=True, suggested_type="C1", notes="human_intervention_ratio=1.00"),
    ))
    transcript = Path(__file__).parent / "fixtures" / "claude_code_transcript.jsonl"
    output = tmp_path / "survey_bad_cases.json"

    runner = CliRunner()
    result = runner.invoke(main, [
        "import-transcripts",
        "--harness", "claude-code",
        "--path", str(transcript),
        "--bench-report", str(output),
        "--bench-harness", "survey-godot-demo",
    ])

    assert result.exit_code == 0
    merged = store.read_session("unknown_2026-06-25_000")
    assert merged.harness == "claude-code"
    assert len(merged.prompts) == 2
    assert merged.system_context["total_tokens"] == 500 + 1200 + 800 + 400
    data = json.loads(output.read_text(encoding="utf-8"))
    row = data["testcases"][0]
    assert row["testcase_id"] == "unknown_2026-06-25_000"
    assert len(row["survey_session"]["prompts"]) == 2
    assert row["survey_session"]["system_context"]["transcript_session_id"].startswith("claude-code_")


def test_import_transcripts_auto_discovers_claude_project_dir(tmp_git_repo: Path, monkeypatch, tmp_path: Path):
    from survey.branch import BranchStore
    from survey.transcripts import claude_project_dir_name
    from survey.models import Outcome, Session, TagInfo

    monkeypatch.chdir(tmp_git_repo)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    store = BranchStore(tmp_git_repo)
    store.init_branch()
    store.write_session(Session(
        session_id="unknown_2026-06-25_000",
        harness="unknown",
        changed_files=["scripts/enemy_patrol.gd", "scenes/enemy.tscn"],
        outcome=Outcome(human_lines_changed=10),
        tag=TagInfo(auto_detected=True, suggested_type="C1", notes="human_intervention_ratio=1.00"),
    ))
    project_dir = tmp_path / ".claude" / "projects" / claude_project_dir_name(tmp_git_repo)
    project_dir.mkdir(parents=True)
    transcript = Path(__file__).parent / "fixtures" / "claude_code_transcript.jsonl"
    (project_dir / "session.jsonl").write_text(transcript.read_text(encoding="utf-8"), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["import-transcripts", "--harness", "claude-code"])

    assert result.exit_code == 0
    assert "Imported 1 transcript(s)" in result.output
    merged = store.read_session("unknown_2026-06-25_000")
    assert len(merged.prompts) == 2
    assert merged.system_context["transcript_match_confidence"] == "high"


def test_import_transcripts_auto_discovers_codex_sessions(tmp_git_repo: Path, monkeypatch, tmp_path: Path):
    from survey.branch import BranchStore
    from survey.models import Outcome, Session, TagInfo

    monkeypatch.chdir(tmp_git_repo)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    store = BranchStore(tmp_git_repo)
    store.init_branch()
    store.write_session(Session(
        session_id="unknown_2026-06-25_000",
        harness="unknown",
        changed_files=["scripts/enemy_patrol.gd", "scenes/enemy.tscn"],
        outcome=Outcome(human_lines_changed=10),
        tag=TagInfo(auto_detected=True, suggested_type="C1", notes="human_intervention_ratio=1.00"),
    ))

    codex_dir = tmp_path / ".codex" / "sessions" / "2026" / "06" / "25"
    codex_dir.mkdir(parents=True)
    transcript = Path(__file__).parent / "fixtures" / "codex_transcript.jsonl"
    text = transcript.read_text(encoding="utf-8").replace("C:\\\\repo\\\\game", str(tmp_git_repo).replace("\\", "\\\\"))
    (codex_dir / "rollout.jsonl").write_text(text, encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["import-transcripts"])

    assert result.exit_code == 0
    assert "Imported 1 transcript(s)" in result.output
    merged = store.read_session("unknown_2026-06-25_000")
    assert merged.harness == "codex"
    assert len(merged.prompts) == 2
    assert merged.system_context["transcript_match_confidence"] == "high"
    assert merged.system_context["codex_session_id"] == "codex123"
    context = store.read_session("codex_2026-06-25_codex123")
    assert context.commits == ["abc1234"]
    assert context.system_context["turn_commits"]["2"] == ["abc1234"]


def test_import_transcripts_codex_ignores_other_repos(tmp_git_repo: Path, monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_git_repo)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    codex_dir = tmp_path / ".codex" / "sessions" / "2026" / "06" / "25"
    codex_dir.mkdir(parents=True)
    transcript = Path(__file__).parent / "fixtures" / "codex_transcript.jsonl"
    (codex_dir / "rollout.jsonl").write_text(transcript.read_text(encoding="utf-8"), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(main, ["import-transcripts", "--harness", "codex"])

    assert result.exit_code == 0
    assert "Imported 0 transcript(s)" in result.output


def test_tag_manual_bad_case_merges_transcript_and_exports_bench(tmp_git_repo: Path, monkeypatch, tmp_path: Path):
    from survey.branch import BranchStore
    from survey.models import Outcome, Session

    monkeypatch.chdir(tmp_git_repo)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    store = BranchStore(tmp_git_repo)
    store.init_branch()
    store.write_session(Session(
        session_id="unknown_2026-06-25_000",
        harness="unknown",
        changed_files=["scripts/enemy_patrol.gd", "scenes/enemy.tscn"],
        outcome=Outcome(ai_lines_changed=5),
    ))

    codex_dir = tmp_path / ".codex" / "sessions" / "2026" / "06" / "25"
    codex_dir.mkdir(parents=True)
    transcript = Path(__file__).parent / "fixtures" / "codex_transcript.jsonl"
    text = transcript.read_text(encoding="utf-8").replace("C:\\\\repo\\\\game", str(tmp_git_repo).replace("\\", "\\\\"))
    (codex_dir / "rollout.jsonl").write_text(text, encoding="utf-8")
    output = tmp_path / "survey_bad_cases.json"

    runner = CliRunner()
    result = runner.invoke(main, [
        "tag",
        "unknown_2026-06-25_000",
        "--type", "B1",
        "--notes", "Timer signal mismatch",
        "--bench-report", str(output),
        "--bench-harness", "survey-godot-demo",
    ])

    assert result.exit_code == 0
    assert "Merged 1 transcript(s)" in result.output
    merged = store.read_session("unknown_2026-06-25_000")
    assert merged.tag.bad_case_type == "B1"
    assert merged.tag.notes == "Timer signal mismatch"
    assert merged.harness == "codex"
    assert len(merged.prompts) == 2
    assert merged.system_context["codex_session_id"] == "codex123"
    data = json.loads(output.read_text(encoding="utf-8"))
    row = data["testcases"][0]
    assert row["category"] == "survey:B1"
    assert len(row["survey_session"]["prompts"]) == 2
    assert row["survey_session"]["system_context"]["codex_session_id"] == "codex123"


def test_init_defaults_name_to_folder(tmp_git_repo: Path, monkeypatch):
    monkeypatch.chdir(tmp_git_repo)
    runner = CliRunner()
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0
    assert tmp_git_repo.name in result.output


def test_init_empty_repo(tmp_empty_git_repo: Path, monkeypatch):
    monkeypatch.chdir(tmp_empty_git_repo)
    runner = CliRunner()
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0
    assert tmp_empty_git_repo.name in result.output
    assert not (tmp_empty_git_repo / "survey.toml").exists()


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


def test_watch_once_empty_repo(tmp_empty_git_repo: Path, monkeypatch):
    monkeypatch.chdir(tmp_empty_git_repo)
    runner = CliRunner()
    result = runner.invoke(main, ["watch", "--once"])
    assert result.exit_code == 0
    assert "[watch] collected 0 session(s); 0 bad case(s)." in result.output


def test_watch_once_writes_bench_report(tmp_empty_git_repo: Path, monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_empty_git_repo)
    output = tmp_path / "survey_bad_cases.json"
    runner = CliRunner()
    result = runner.invoke(main, [
        "watch",
        "--once",
        "--bench-report", str(output),
        "--bench-harness", "survey-godot-demo",
    ])

    assert result.exit_code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["harness"] == "survey-godot-demo"
    assert data["count"] == 0
    assert data["testcases"] == []


def test_report_auto_inits(tmp_git_repo: Path, monkeypatch):
    monkeypatch.chdir(tmp_git_repo)
    runner = CliRunner()
    result = runner.invoke(main, ["report"])
    assert result.exit_code == 0
    assert "Total sessions: 0" in result.output
