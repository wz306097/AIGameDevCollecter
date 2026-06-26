from pathlib import Path

from survey.adapters import get_adapter
from survey.adapters.codex import CodexAdapter
from survey.models import HarnessEvent, Session


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "codex_transcript.jsonl"


def test_parse_transcript_returns_session():
    adapter = CodexAdapter()
    session = adapter.parse_transcript(FIXTURE_PATH)
    assert isinstance(session, Session)
    assert session.harness == "codex"
    assert session.session_id.startswith("codex_")


def test_get_adapter_loads_codex_adapter():
    adapter = get_adapter("codex")
    assert isinstance(adapter, CodexAdapter)


def test_parse_transcript_extracts_prompts():
    adapter = CodexAdapter()
    session = adapter.parse_transcript(FIXTURE_PATH)
    assert len(session.prompts) == 2
    assert session.prompts[0].user_message == "Add enemy patrol between two points."
    assert session.prompts[1].user_message == "Wrong, the timer signal is not connected."


def test_parse_transcript_extracts_tool_calls_and_changed_files():
    adapter = CodexAdapter()
    session = adapter.parse_transcript(FIXTURE_PATH)
    assert "apply_patch:scripts/enemy_patrol.gd" in session.prompts[0].tool_calls
    assert "apply_patch:scenes/enemy.tscn" in session.prompts[0].tool_calls
    assert any(call.startswith("shell_command:git diff") for call in session.prompts[1].tool_calls)
    assert "scripts/enemy_patrol.gd" in session.changed_files
    assert "scenes/enemy.tscn" in session.changed_files


def test_parse_transcript_records_context_and_tokens():
    adapter = CodexAdapter()
    session = adapter.parse_transcript(FIXTURE_PATH)
    assert session.system_context["transcript_format"] == "codex-jsonl"
    assert session.system_context["codex_session_id"] == "codex123"
    assert session.system_context["total_tokens"] == 1234
    assert session.commits == ["abc1234"]
    assert session.system_context["turn_commits"]["2"] == ["abc1234"]
    assert session.timestamps["started"] == "2026-06-25T08:00:00Z"
    assert session.timestamps["ended"] == "2026-06-25T08:10:11Z"


def test_extract_events_returns_harness_events():
    adapter = CodexAdapter()
    events = adapter.extract_events(FIXTURE_PATH)
    assert all(isinstance(e, HarnessEvent) for e in events)
    paths = {e.payload["file_path"] for e in events}
    assert paths == {"scripts/enemy_patrol.gd", "scenes/enemy.tscn"}
