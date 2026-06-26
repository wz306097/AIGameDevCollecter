from __future__ import annotations

import glob
import json
from pathlib import Path

from survey.models import Session
from survey.storage import ensure_store

AUTO_TRANSCRIPT_HARNESSES = ("claude-code", "codex")


def import_transcripts_once(
    repo_root: Path,
    harness: str | None,
    path: Path | None,
) -> tuple[int, int, int]:
    """Import Claude Code/Codex transcript context into matching Survey sessions.

    Returns ``(imported, newly_flagged, skipped)``.
    """
    from survey.adapters import get_adapter

    ensure_store(repo_root)
    imported = 0
    flagged = 0
    skipped = 0
    candidate_paths: set[Path] = set()
    imported_paths: set[Path] = set()

    for harness_name in _default_transcript_harnesses(harness):
        adapter = get_adapter(harness_name)
        for transcript in discover_transcript_paths(repo_root, harness_name, path):
            resolved = transcript.resolve()
            candidate_paths.add(resolved)
            if resolved in imported_paths:
                continue
            try:
                session = adapter.parse_transcript(transcript)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, NotImplementedError):
                if harness:
                    skipped += 1
                continue
            if not session.prompts and not session.changed_files:
                if harness:
                    skipped += 1
                continue
            was_flagged, _ = detect_and_store_session(repo_root, session)
            imported += 1
            imported_paths.add(resolved)
            if was_flagged:
                flagged += 1

    if not harness:
        skipped = len(candidate_paths - imported_paths)
    return imported, flagged, skipped


def merge_transcript_context_into_session(
    repo_root: Path,
    target: Session,
    harness: str | None,
    path: Path | None,
) -> tuple[Session, int, int]:
    """Merge matching transcript turns into one manually tagged session."""
    from survey.adapters import get_adapter
    from survey.config import get_merged_config
    from survey.inference import find_task_group
    from survey.metrics import compute_metrics

    imported = 0
    skipped = 0
    seen: set[Path] = set()

    for harness_name in _default_transcript_harnesses(harness):
        adapter = get_adapter(harness_name)
        for transcript in discover_transcript_paths(repo_root, harness_name, path):
            resolved = transcript.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                session = adapter.parse_transcript(transcript)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError, NotImplementedError):
                skipped += 1
                continue

            target_id, confidence = find_task_group(session, [target])
            if target_id != target.session_id or confidence not in {"high", "low"}:
                skipped += 1
                continue

            session = context_for_target_session(session, target)
            target.prompts = session.prompts or target.prompts
            target.system_context.update(session.system_context)
            target.harness = session.harness or target.harness
            target.changed_files = sorted(set(target.changed_files) | set(session.changed_files))
            target.timestamps.update({k: v for k, v in session.timestamps.items() if v})
            target.system_context["transcript_session_id"] = session.session_id
            target.system_context["transcript_match_confidence"] = confidence
            imported += 1

    if imported:
        config = get_merged_config(repo_root)
        target.outcome = compute_metrics(target, repo_root=repo_root, config=config)
    return target, imported, skipped


def detect_and_store_session(repo_root: Path, session: Session) -> tuple[bool, str | None]:
    """Compute metrics/tag and persist a git-derived or transcript-derived session.

    If a transcript overlaps an existing git-diff session, its prompt/output
    context is merged into that existing session so bad cases gain agent context
    without creating duplicate report rows.
    """
    from survey.badcase import detect_bad_case
    from survey.branch import BranchStore
    from survey.config import get_merged_config
    from survey.inference import find_task_group
    from survey.metrics import compute_metrics

    store = BranchStore(repo_root)
    config = get_merged_config(repo_root)
    existing = store.list_sessions()
    target_id, confidence = find_task_group(session, existing)

    if target_id and confidence in {"high", "low"}:
        source_session = session
        target = store.read_session(target_id)
        manual_tag = target.tag if target.tag and target.tag.bad_case_type else None
        target_context = context_for_target_session(source_session, target)
        target.prompts = target_context.prompts or target.prompts
        target.system_context.update(target_context.system_context)
        target.harness = target_context.harness or target.harness
        target.changed_files = sorted(set(target.changed_files) | set(target_context.changed_files))
        target.timestamps.update({k: v for k, v in target_context.timestamps.items() if v})
        target.system_context["transcript_session_id"] = target_context.session_id
        target.system_context["transcript_match_confidence"] = confidence
        target.outcome = compute_metrics(target, repo_root=repo_root, config=config)
        tag_info = detect_bad_case(target)
        if manual_tag:
            target.tag = manual_tag
        elif tag_info:
            target.tag = tag_info
        store.write_session(target)
        if source_session.session_id != target.session_id and (
            source_session.prompts or source_session.system_context
        ):
            source_session.outcome = compute_metrics(source_session, repo_root=repo_root, config=config)
            store.write_session(source_session)
        return bool(tag_info), target.session_id

    session.outcome = compute_metrics(session, repo_root=repo_root, config=config)
    tag_info = detect_bad_case(session)
    if tag_info:
        session.tag = tag_info
    store.write_session(session)
    return bool(tag_info), session.session_id


def context_for_target_session(source: Session, target: Session) -> Session:
    """Return transcript context narrowed to the target commit when possible."""
    turn_commits = source.system_context.get("turn_commits", {})
    if not isinstance(turn_commits, dict) or not target.commits:
        return source

    target_commits = set(target.commits)
    matching_turns = {
        int(turn)
        for turn, commits in turn_commits.items()
        if isinstance(commits, list) and target_commits & set(str(c) for c in commits)
    }
    if not matching_turns:
        return source

    turn_files = source.system_context.get("turn_files", {})
    selected_files: set[str] = set(target.changed_files)
    if isinstance(turn_files, dict):
        for turn in matching_turns:
            files = turn_files.get(str(turn), [])
            if isinstance(files, list):
                selected_files.update(str(f) for f in files if f)

    narrowed_context = dict(source.system_context)
    narrowed_context["transcript_filtered_to_commits"] = sorted(target_commits)
    narrowed_context["transcript_filtered_turns"] = sorted(matching_turns)

    return Session(
        session_id=source.session_id,
        harness=source.harness,
        config=source.config,
        prompts=[turn for turn in source.prompts if turn.turn in matching_turns],
        system_context=narrowed_context,
        changed_files=sorted(selected_files),
        commits=sorted(target_commits),
        timestamps=source.timestamps,
    )


def discover_transcript_paths(repo_root: Path, harness: str, explicit_path: Path | None = None) -> list[Path]:
    if explicit_path is not None:
        return _transcript_paths(explicit_path)

    from survey.config import get_merged_config

    candidates: list[Path] = []
    seen: set[Path] = set()

    def add_path(path: Path) -> None:
        for transcript in _transcript_paths(path):
            if harness == "codex" and not _codex_transcript_matches_repo(transcript, repo_root):
                continue
            resolved = transcript.resolve()
            if resolved not in seen:
                seen.add(resolved)
                candidates.append(transcript)

    if harness == "claude-code":
        project_dir = Path.home() / ".claude" / "projects" / claude_project_dir_name(repo_root)
        if project_dir.exists():
            add_path(project_dir)
    elif harness == "codex":
        sessions_dir = Path.home() / ".codex" / "sessions"
        if sessions_dir.exists():
            add_path(sessions_dir)

    config = get_merged_config(repo_root)
    source = config.get("global", {}).get("transcript_sources", {}).get(harness, "")
    sources = source if isinstance(source, list) else [source]
    for pattern in sources:
        if not pattern:
            continue
        expanded = str(Path(pattern).expanduser())
        for match in glob.glob(expanded, recursive=True):
            path = Path(match)
            if path.exists():
                add_path(path)

    return sorted(candidates)


def claude_project_dir_name(repo_root: Path) -> str:
    return str(repo_root.resolve()).replace("\\", "-").replace("/", "-").replace(":", "")


def _default_transcript_harnesses(harness: str | None) -> tuple[str, ...]:
    return (harness,) if harness else AUTO_TRANSCRIPT_HARNESSES


def _transcript_paths(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(
        p for p in path.rglob("*")
        if p.is_file() and p.suffix.lower() == ".jsonl"
    )


def _codex_transcript_matches_repo(path: Path, repo_root: Path) -> bool:
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                record = json.loads(line)
                payload = record.get("payload", {})
                if record.get("type") == "session_meta":
                    cwd = payload.get("cwd", "")
                    roots = payload.get("workspace_roots", [])
                    if _path_points_at_repo(cwd, repo_root):
                        return True
                    if any(_path_points_at_repo(str(root), repo_root) for root in roots if root):
                        return True
                    return False
                if payload.get("type") == "turn_context":
                    cwd = payload.get("cwd", "")
                    roots = payload.get("workspace_roots", [])
                    if _path_points_at_repo(cwd, repo_root):
                        return True
                    if any(_path_points_at_repo(str(root), repo_root) for root in roots if root):
                        return True
                    return False
    except (OSError, json.JSONDecodeError, TypeError):
        return False
    return False


def _path_points_at_repo(value: str, repo_root: Path) -> bool:
    if not value:
        return False
    try:
        candidate = Path(value).expanduser().resolve()
        root = repo_root.resolve()
    except (OSError, ValueError):
        return False
    return candidate == root or root in candidate.parents
