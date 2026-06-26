from __future__ import annotations

import os

from survey.models import Session


def _dir_prefix(path: str) -> str:
    return os.path.dirname(path)


def _extract_files_for_turn(turn) -> set[str]:
    files: set[str] = set()
    for tc in turn.tool_calls:
        if ":" in tc:
            files.add(tc.split(":", 1)[1])
    return files


def detect_multi_task(session: Session) -> tuple[bool, list[dict]]:
    if not session.prompts:
        return False, [{"turn_range": [], "files": list(session.changed_files)}]

    groups: list[dict] = []
    current_files: set[str] = set()
    current_dirs: set[str] = set()
    current_turns: list[int] = []

    for turn in session.prompts:
        turn_files = _extract_files_for_turn(turn)
        if not turn_files:
            if current_turns:
                current_turns.append(turn.turn)
            continue

        turn_dirs = {_dir_prefix(f) for f in turn_files}

        if not current_files:
            current_files = turn_files
            current_dirs = turn_dirs
            current_turns = [turn.turn]
        elif current_dirs & turn_dirs or current_files & turn_files:
            current_files.update(turn_files)
            current_dirs.update(turn_dirs)
            current_turns.append(turn.turn)
        else:
            groups.append({
                "turn_range": [current_turns[0], current_turns[-1]],
                "files": sorted(current_files),
            })
            current_files = turn_files
            current_dirs = turn_dirs
            current_turns = [turn.turn]

    if current_turns:
        groups.append({
            "turn_range": [current_turns[0], current_turns[-1]],
            "files": sorted(current_files),
        })

    if not groups:
        groups = [{"turn_range": [], "files": list(session.changed_files)}]

    return len(groups) > 1, groups


def _jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def find_task_group(
    session: Session,
    existing_sessions: list[Session],
) -> tuple[str | None, str]:
    session_commits = set(session.commits)
    if session_commits:
        for existing in existing_sessions:
            if session_commits & set(existing.commits):
                return existing.session_id, "high"

    session_files = set(session.changed_files)
    if not session_files:
        return None, "none"

    best_id = None
    best_score = 0.0

    for existing in existing_sessions:
        existing_files = set(existing.changed_files)
        score = _jaccard(session_files, existing_files)
        if score > best_score:
            best_score = score
            best_id = existing.session_id

    if best_score > 0.5:
        return best_id, "high"
    elif best_score >= 0.2:
        return best_id, "low"
    else:
        return None, "none"
