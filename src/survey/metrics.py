from __future__ import annotations

from datetime import datetime
from pathlib import Path

from survey.git_ops import git_run
from survey.models import Session, Outcome


def _ai_author_patterns(config: dict | None) -> list[str]:
    if not config:
        return []
    git_cfg = config.get("global", {}).get("git", {})
    return [p.lower() for p in git_cfg.get("ai_authors", []) if p]


def _commit_is_ai(repo_root: Path, sha: str, patterns: list[str]) -> bool:
    if not patterns:
        return False
    try:
        message = git_run(["log", "-1", "--pretty=format:%B", sha], cwd=repo_root)
    except Exception:
        return False
    trailers = [
        line for line in message.splitlines()
        if line.lower().startswith("co-authored-by:")
    ]
    blob = "\n".join(trailers).lower()
    return any(p in blob for p in patterns)


def _commit_line_count(repo_root: Path, sha: str) -> int:
    try:
        out = git_run(["show", "--numstat", "--format=", sha], cwd=repo_root)
    except Exception:
        return 0
    total = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        added, deleted = parts[0], parts[1]
        if added.isdigit():
            total += int(added)
        if deleted.isdigit():
            total += int(deleted)
    return total


def _attribute_lines(session: Session, repo_root: Path, config: dict | None) -> tuple[int, int]:
    patterns = _ai_author_patterns(config)
    ai_lines = 0
    human_lines = 0
    for sha in session.commits:
        lines = _commit_line_count(repo_root, sha)
        if _commit_is_ai(repo_root, sha, patterns):
            ai_lines += lines
        else:
            human_lines += lines
    return ai_lines, human_lines


def compute_metrics(session: Session, repo_root=None, config=None) -> Outcome:
    rounds = len(session.prompts) if session.prompts else 0

    verification_pass = True
    if session.verification:
        verification_pass = session.verification.l0_pass and session.verification.l1_pass

    first_pass = verification_pass and rounds <= 1

    duration = 0.0
    started = session.timestamps.get("started", "")
    ended = session.timestamps.get("ended", "")
    if started and ended:
        try:
            t_start = datetime.fromisoformat(started.replace("Z", "+00:00"))
            t_end = datetime.fromisoformat(ended.replace("Z", "+00:00"))
            duration = (t_end - t_start).total_seconds() / 60
        except (ValueError, TypeError):
            pass

    token_cost = session.system_context.get("total_tokens", 0)

    ai_lines = 0
    human_lines = 0
    if repo_root is not None and session.commits:
        ai_lines, human_lines = _attribute_lines(session, Path(repo_root), config)

    return Outcome(
        first_pass_success=first_pass,
        rounds_to_resolution=max(rounds, 1),
        ai_lines_changed=ai_lines,
        human_lines_changed=human_lines,
        token_cost=token_cost,
        session_duration_minutes=duration,
    )
