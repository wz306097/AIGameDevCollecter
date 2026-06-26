from pathlib import Path

from survey.adapters.claude_code import ClaudeCodeAdapter
from survey.adapters import get_adapter
from survey.models import Session, HarnessEvent


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "claude_code_transcript.jsonl"


def test_parse_transcript_returns_session():
    adapter = ClaudeCodeAdapter()
    session = adapter.parse_transcript(FIXTURE_PATH)
    assert isinstance(session, Session)
    assert session.harness == "claude-code"
    assert session.session_id.startswith("claude-code_")


def test_get_adapter_loads_claude_code_adapter():
    adapter = get_adapter("claude-code")
    assert isinstance(adapter, ClaudeCodeAdapter)


def test_parse_transcript_extracts_prompts():
    adapter = ClaudeCodeAdapter()
    session = adapter.parse_transcript(FIXTURE_PATH)
    assert len(session.prompts) == 2
    assert "巡逻" in session.prompts[0].user_message
    assert "Timer" in session.prompts[1].user_message


def test_parse_transcript_extracts_tool_calls():
    adapter = ClaudeCodeAdapter()
    session = adapter.parse_transcript(FIXTURE_PATH)
    assert "Write:scripts/enemy_patrol.gd" in session.prompts[0].tool_calls
    assert "Write:scenes/enemy.tscn" in session.prompts[0].tool_calls
    assert "Edit:scripts/enemy_patrol.gd" in session.prompts[1].tool_calls


def test_parse_transcript_extracts_summary():
    adapter = ClaudeCodeAdapter()
    session = adapter.parse_transcript(FIXTURE_PATH)
    assert "状态机" in session.prompts[0].assistant_summary
    assert "timeout" in session.prompts[1].assistant_summary


def test_parse_transcript_extracts_changed_files():
    adapter = ClaudeCodeAdapter()
    session = adapter.parse_transcript(FIXTURE_PATH)
    assert "scripts/enemy_patrol.gd" in session.changed_files
    assert "scenes/enemy.tscn" in session.changed_files


def test_parse_transcript_records_timestamps():
    adapter = ClaudeCodeAdapter()
    session = adapter.parse_transcript(FIXTURE_PATH)
    assert session.timestamps["started"] == "2026-06-18T10:00:00Z"
    assert session.timestamps["ended"] == "2026-06-18T10:12:00Z"


def test_parse_transcript_computes_token_cost():
    adapter = ClaudeCodeAdapter()
    session = adapter.parse_transcript(FIXTURE_PATH)
    assert session.system_context.get("total_tokens") == 500 + 1200 + 800 + 400


def test_extract_events_returns_harness_events():
    adapter = ClaudeCodeAdapter()
    events = adapter.extract_events(FIXTURE_PATH)
    file_writes = [e for e in events if e.event_type == "file_write"]
    assert len(file_writes) == 3
    paths = {e.payload["file_path"] for e in file_writes}
    assert "scripts/enemy_patrol.gd" in paths
    assert "scenes/enemy.tscn" in paths
