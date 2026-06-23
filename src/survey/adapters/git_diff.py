from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from survey.adapters import register
from survey.git_ops import git_run
from survey.models import HarnessEvent, Session


@register("unknown")
class GitDiffAdapter:
    def parse_transcript(self, path: Path) -> Session:
        raise NotImplementedError("Git-diff adapter does not parse transcripts. Use infer_sessions() instead.")

    def extract_events(self, path: Path) -> list[HarnessEvent]:
        raise NotImplementedError("Git-diff adapter does not parse transcript files. Use extract_events_from_repo().")

    def infer_sessions(
        self,
        repo_root: Path,
        since: str,
        until: str,
        gap_minutes: int = 30,
    ) -> list[Session]:
        log_output = git_run(
            ["log", f"--since={since}", f"--until={until}", "--pretty=format:%H|%aI", "--name-only"],
            cwd=repo_root,
        )
        commits: list[dict] = []
        current: dict | None = None
        for line in log_output.splitlines():
            line = line.strip()
            if not line:
                continue
            if "|" in line and len(line.split("|")[0]) == 40:
                parts = line.split("|", 1)
                current = {"hash": parts[0], "timestamp": parts[1], "files": []}
                commits.append(current)
            elif current is not None:
                current["files"].append(line)

        if not commits:
            return []

        groups: list[list[dict]] = [[commits[0]]]
        for commit in commits[1:]:
            try:
                t1 = datetime.fromisoformat(groups[-1][-1]["timestamp"])
                t2 = datetime.fromisoformat(commit["timestamp"])
                diff_min = abs((t1 - t2).total_seconds()) / 60
            except (ValueError, TypeError):
                diff_min = gap_minutes + 1
            if diff_min <= gap_minutes:
                groups[-1].append(commit)
            else:
                groups.append([commit])

        sessions: list[Session] = []
        for i, group in enumerate(groups):
            all_files: set[str] = set()
            all_hashes: list[str] = []
            timestamps_list: list[str] = []
            for c in group:
                all_files.update(c["files"])
                all_hashes.append(c["hash"][:7])
                timestamps_list.append(c["timestamp"])
            date_str = timestamps_list[0][:10] if timestamps_list else datetime.now(timezone.utc).strftime("%Y-%m-%d")
            sessions.append(Session(
                session_id=f"unknown_{date_str}_{i:03d}",
                harness="unknown",
                changed_files=sorted(all_files),
                commits=all_hashes,
                timestamps={
                    "started": timestamps_list[-1] if timestamps_list else "",
                    "ended": timestamps_list[0] if timestamps_list else "",
                },
            ))
        return sessions
