from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from survey.adapters import register
from survey.models import HarnessEvent, Session, Turn


_PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)
_PATCH_MOVE_RE = re.compile(r"^\*\*\* Move to: (.+)$", re.MULTILINE)
_PROJECT_FILE_RE = re.compile(
    r"(?P<path>\.gitignore|(?:res://)?[A-Za-z0-9_./\\:-]+"
    r"(?:\.gd|\.tscn|\.tres|\.godot|\.uid|\.gdshader|\.cfg|\.json|\.toml|\.md))"
)
_COMMIT_OUTPUT_RES = (
    re.compile(r"^\[[^\]]+\s([0-9a-f]{7,40})\]", re.MULTILINE),
    re.compile(r"^([0-9a-f]{7,40})\s+.+$", re.MULTILINE),
)


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
            continue
        stripped = line.strip()
        if stripped:
            summary_lines.append(stripped)
    return "\n".join(summary_lines[:10])


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text") or "")
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(p for p in parts if p)


def _is_context_message(text: str) -> bool:
    stripped = text.strip()
    if not stripped.startswith("<"):
        return False
    prefix = stripped[:300]
    context_tags = (
        "environment_context",
        "permissions instructions",
        "skills_instructions",
        "plugins_instructions",
        "collaboration_mode",
    )
    return any(tag in prefix for tag in context_tags)


def _json_arguments(arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if not isinstance(arguments, str):
        return {}
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_file_path(file_path: str, cwd: str | None = None) -> str:
    cleaned = file_path.strip().strip('"').strip("'")
    if cleaned.startswith("res://"):
        cleaned = cleaned.removeprefix("res://")
    if cleaned.startswith(("a/", "b/")):
        cleaned = cleaned[2:]
    if not cleaned:
        return ""

    path = Path(cleaned)
    if path.is_absolute() and cwd:
        try:
            cleaned = str(path.resolve().relative_to(Path(cwd).resolve()))
        except (OSError, ValueError):
            cleaned = str(path)
    return cleaned.replace("\\", "/")


def _extract_file_paths(text: Any, cwd: str | None = None) -> set[str]:
    if not isinstance(text, str) or not text:
        return set()
    files: set[str] = set()
    for match in _PROJECT_FILE_RE.finditer(text):
        normalized = _normalize_file_path(match.group("path"), cwd)
        if normalized and "://" not in normalized:
            files.add(normalized)
    return files


def _extract_commit_hashes(text: Any) -> list[str]:
    if not isinstance(text, str) or not text:
        return []
    commits: list[str] = []
    seen: set[str] = set()
    for pattern in _COMMIT_OUTPUT_RES:
        for match in pattern.finditer(text):
            commit = match.group(1)
            if commit not in seen:
                seen.add(commit)
                commits.append(commit)
    return commits


def _extract_patch_files(arguments: Any, cwd: str | None = None) -> set[str]:
    patch = arguments if isinstance(arguments, str) else ""
    if not patch:
        return set()
    paths = set(_PATCH_FILE_RE.findall(patch))
    paths.update(_PATCH_MOVE_RE.findall(patch))
    return {p for p in (_normalize_file_path(path, cwd) for path in paths) if p}


def _extract_shell_hint(arguments: Any) -> str:
    parsed = _json_arguments(arguments)
    command = parsed.get("command", "")
    if isinstance(command, str) and command:
        return " ".join(command.split())[:160]
    if isinstance(arguments, str):
        return " ".join(arguments.split())[:160]
    return ""


def _format_tool_call(name: str, arguments: Any, cwd: str | None = None) -> tuple[list[str], set[str]]:
    if name == "apply_patch":
        files = _extract_patch_files(arguments, cwd)
        if files:
            return [f"apply_patch:{file_path}" for file_path in sorted(files)], files
        return ["apply_patch"], set()

    if name == "shell_command":
        hint = _extract_shell_hint(arguments)
        files = _extract_file_paths(hint, cwd)
        return [f"shell_command:{hint}" if hint else "shell_command"], files

    hint = _extract_shell_hint(arguments)
    return [f"{name}:{hint}" if hint else name], set()


def _metadata_from_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for record in records:
        payload = record.get("payload", {})
        if record.get("type") == "session_meta" and isinstance(payload, dict):
            metadata.update(payload)
            continue
        if payload.get("type") == "turn_context":
            metadata.setdefault("cwd", payload.get("cwd", ""))
            metadata.setdefault("workspace_roots", payload.get("workspace_roots", []))
    return metadata


def _total_tokens(records: list[dict[str, Any]]) -> int:
    total = 0
    for record in records:
        payload = record.get("payload", {})
        if payload.get("type") != "token_count":
            continue
        info = payload.get("info", {})
        usage = info.get("total_token_usage", {})
        value = usage.get("total_tokens", 0)
        if isinstance(value, int):
            total = max(total, value)
    return total


@register("codex")
class CodexAdapter:
    def parse_transcript(self, path: Path) -> Session:
        records = _read_jsonl(path)
        metadata = _metadata_from_records(records)
        cwd = metadata.get("cwd") if isinstance(metadata.get("cwd"), str) else None

        turns: list[Turn] = []
        changed_files: set[str] = set()
        commits: list[str] = []
        seen_commits: set[str] = set()
        call_turns: dict[str, int] = {}
        turn_files: dict[int, set[str]] = {}
        turn_commits: dict[int, set[str]] = {}
        timestamps: list[str] = []
        pending_user: str | None = None
        current_turn: Turn | None = None
        turn_num = 0

        def add_commit(commit: str, turn: int | None = None) -> None:
            if commit not in seen_commits:
                seen_commits.add(commit)
                commits.append(commit)
            if turn is not None:
                turn_commits.setdefault(turn, set()).add(commit)

        for record in records:
            ts = record.get("timestamp", "")
            if ts:
                timestamps.append(ts)

            if record.get("type") != "response_item":
                continue
            payload = record.get("payload", {})
            item_type = payload.get("type")

            if item_type == "message":
                role = payload.get("role")
                text = _message_text(payload.get("content", "")).strip()
                if not text:
                    continue
                if role == "user":
                    if _is_context_message(text):
                        continue
                    pending_user = text
                    current_turn = None
                elif role == "assistant":
                    summary = _summarize_assistant(text)
                    if pending_user is not None:
                        turn_num += 1
                        current_turn = Turn(
                            turn=turn_num,
                            user_message=pending_user,
                            assistant_summary=summary,
                            tool_calls=[],
                        )
                        turns.append(current_turn)
                        pending_user = None
                    elif current_turn is not None and summary:
                        current_turn.assistant_summary = "\n".join(
                            p for p in [current_turn.assistant_summary, summary] if p
                        )

            elif item_type == "function_call":
                if current_turn is None and pending_user is not None:
                    turn_num += 1
                    current_turn = Turn(
                        turn=turn_num,
                        user_message=pending_user,
                        assistant_summary="",
                        tool_calls=[],
                    )
                    turns.append(current_turn)
                    pending_user = None

                name = str(payload.get("name") or "")
                if not name:
                    continue
                formatted, files = _format_tool_call(name, payload.get("arguments", ""), cwd)
                changed_files.update(files)
                if current_turn is not None:
                    current_turn.tool_calls.extend(formatted)
                    if files:
                        turn_files.setdefault(current_turn.turn, set()).update(files)
                    call_id = payload.get("call_id")
                    if call_id:
                        call_turns[str(call_id)] = current_turn.turn

            elif item_type == "function_call_output":
                call_id = payload.get("call_id")
                turn = call_turns.get(str(call_id)) if call_id else None
                output = payload.get("output", "")
                output_files = _extract_file_paths(output, cwd)
                changed_files.update(output_files)
                if turn is not None and output_files:
                    turn_files.setdefault(turn, set()).update(output_files)
                for commit in _extract_commit_hashes(output):
                    add_commit(commit, turn)

        started = metadata.get("timestamp") or (timestamps[0] if timestamps else "")
        ended = timestamps[-1] if timestamps else started
        date_str = str(started)[:10] if started else datetime.now().strftime("%Y-%m-%d")
        session_id_raw = metadata.get("id") or path.stem
        total_tokens = _total_tokens(records)

        context = {
            "transcript_format": "codex-jsonl",
            "transcript_path": str(path),
            "codex_session_id": session_id_raw,
        }
        for key in ("cwd", "originator", "cli_version", "model_provider", "model"):
            value = metadata.get(key)
            if value:
                context[key] = value
        if total_tokens:
            context["total_tokens"] = total_tokens
        if turn_files:
            context["turn_files"] = {str(k): sorted(v) for k, v in sorted(turn_files.items())}
        if turn_commits:
            context["turn_commits"] = {str(k): sorted(v) for k, v in sorted(turn_commits.items())}

        return Session(
            session_id=f"codex_{date_str}_{session_id_raw}",
            harness="codex",
            prompts=turns,
            system_context=context,
            changed_files=sorted(changed_files),
            commits=commits,
            timestamps={"started": started, "ended": ended},
        )

    def extract_events(self, path: Path) -> list[HarnessEvent]:
        records = _read_jsonl(path)
        metadata = _metadata_from_records(records)
        cwd = metadata.get("cwd") if isinstance(metadata.get("cwd"), str) else None
        session_id = str(metadata.get("id") or path.stem)
        events: list[HarnessEvent] = []
        event_counter = 0

        for record in records:
            if record.get("type") != "response_item":
                continue
            payload = record.get("payload", {})
            if payload.get("type") != "function_call" or payload.get("name") != "apply_patch":
                continue
            for file_path in sorted(_extract_patch_files(payload.get("arguments", ""), cwd)):
                event_counter += 1
                events.append(HarnessEvent(
                    event_id=f"evt_{event_counter:06d}",
                    harness="codex",
                    session_id=session_id,
                    timestamp=record.get("timestamp", ""),
                    event_type="file_write",
                    payload={"file_path": file_path, "action": "edit"},
                ))

        return events
