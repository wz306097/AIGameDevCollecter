from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from survey.adapters import register
from survey.models import HarnessEvent, Turn, Session


def _summarize_assistant(content: str) -> str:
    lines = content.strip().splitlines()
    code_block = False
    summary_lines: list[str] = []
    block_lines: list[str] = []
    for line in lines:
        if line.strip().startswith("```"):
            code_block = not code_block
            if code_block:
                block_lines = []
            else:
                sig_pattern = re.compile(r"^\s*(func |def |class |export )")
                sigs = [l.strip() for l in block_lines if sig_pattern.match(l)]
                sig_str = " + ".join(sigs[:3]) if sigs else "..."
                summary_lines.append(f"[code: {len(block_lines)} lines, {sig_str}]")
            continue
        if code_block:
            block_lines.append(line)
        else:
            stripped = line.strip()
            if stripped and not _is_filler(stripped):
                summary_lines.append(stripped)
    return "\n".join(summary_lines[:10])


def _is_filler(line: str) -> bool:
    filler_patterns = [
        "I'll ", "Let me ", "I will ", "Sure", "Of course", "Here's what",
        "I've ", "I have ", "Done!", "完成", "好的",
    ]
    return any(line.startswith(p) for p in filler_patterns)


def _extract_tool_calls(tool_calls: list[dict]) -> tuple[list[str], set[str]]:
    formatted: list[str] = []
    files: set[str] = set()
    for tc in tool_calls:
        tool = tc.get("tool", "")
        inp = tc.get("input", {})
        file_path = inp.get("file_path", "")
        if file_path:
            formatted.append(f"{tool}:{file_path}")
            files.add(file_path)
    return formatted, files


@register("claude-code")
class ClaudeCodeAdapter:
    def parse_transcript(self, path: Path) -> Session:
        messages = _read_jsonl(path)
        turns: list[Turn] = []
        all_files: set[str] = set()
        total_tokens = 0
        timestamps: list[str] = []
        session_id_raw = None

        turn_num = 0
        pending_human: str | None = None

        for msg in messages:
            ts = msg.get("timestamp", "")
            if ts:
                timestamps.append(ts)
            if msg.get("session_id"):
                session_id_raw = msg["session_id"]

            if msg["type"] == "human":
                pending_human = msg["message"]["content"]

            elif msg["type"] == "assistant" and pending_human is not None:
                turn_num += 1
                content = msg["message"]["content"]
                tool_calls_raw = msg.get("tool_calls", [])
                tc_formatted, tc_files = _extract_tool_calls(tool_calls_raw)
                all_files.update(tc_files)

                usage = msg.get("usage", {})
                total_tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

                turns.append(Turn(
                    turn=turn_num,
                    user_message=pending_human,
                    assistant_summary=_summarize_assistant(content),
                    tool_calls=tc_formatted,
                ))
                pending_human = None

        date_str = datetime.now().strftime("%Y-%m-%d")
        if timestamps:
            try:
                date_str = timestamps[0][:10]
            except (IndexError, TypeError):
                pass
        session_id = f"claude-code_{date_str}_{session_id_raw or '001'}"

        return Session(
            session_id=session_id,
            harness="claude-code",
            prompts=turns,
            system_context={"total_tokens": total_tokens},
            changed_files=sorted(all_files),
            timestamps={
                "started": timestamps[0] if timestamps else "",
                "ended": timestamps[-1] if timestamps else "",
            },
        )

    def extract_events(self, path: Path) -> list[HarnessEvent]:
        messages = _read_jsonl(path)
        events: list[HarnessEvent] = []
        session_id = None
        event_counter = 0

        for msg in messages:
            if msg.get("session_id"):
                session_id = msg["session_id"]
            if msg["type"] != "assistant":
                continue
            for tc in msg.get("tool_calls", []):
                tool = tc.get("tool", "")
                inp = tc.get("input", {})
                file_path = inp.get("file_path", "")
                if tool in ("Write", "Edit") and file_path:
                    event_counter += 1
                    events.append(HarnessEvent(
                        event_id=f"evt_{event_counter:06d}",
                        harness="claude-code",
                        session_id=session_id or "",
                        timestamp=msg.get("timestamp", ""),
                        event_type="file_write",
                        payload={"file_path": file_path, "action": "create" if tool == "Write" else "edit"},
                    ))
        return events


def _read_jsonl(path: Path) -> list[dict]:
    messages: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                messages.append(json.loads(line))
    return messages
