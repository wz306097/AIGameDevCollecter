from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from survey.git_ops import git_run
from survey.models import Session

BRANCH_NAME = "survey"


class BranchStore:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def branch_exists(self) -> bool:
        try:
            git_run(["rev-parse", "--verify", f"refs/heads/{BRANCH_NAME}"], cwd=self.repo_root)
            return True
        except subprocess.CalledProcessError:
            return False

    def init_branch(self) -> None:
        if self.branch_exists():
            return
        current_branch = git_run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=self.repo_root).strip()
        git_run(["checkout", "--orphan", BRANCH_NAME], cwd=self.repo_root)
        git_run(["rm", "-rf", "."], cwd=self.repo_root)
        for dirname in ("sessions", "transcripts", "reports"):
            d = self.repo_root / dirname
            d.mkdir(exist_ok=True)
            (d / ".gitkeep").touch()
            git_run(["add", f"{dirname}/.gitkeep"], cwd=self.repo_root)
        default_config = '[project]\nname = ""\nengine = "godot"\nengine_version = "4.3"\n'
        (self.repo_root / "survey.toml").write_text(default_config)
        git_run(["add", "survey.toml"], cwd=self.repo_root)
        git_run(["commit", "-m", "Initialize survey branch"], cwd=self.repo_root)
        git_run(["checkout", current_branch], cwd=self.repo_root)

    def _read_file(self, path: str) -> str:
        return git_run(["show", f"{BRANCH_NAME}:{path}"], cwd=self.repo_root)

    def _write_file(self, path: str, content: str, message: str) -> None:
        env_copy = os.environ.copy()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".idx") as tmp:
            tmp_index = tmp.name
        try:
            env_copy["GIT_INDEX_FILE"] = tmp_index
            tree_output = git_run(["rev-parse", f"{BRANCH_NAME}^{{tree}}"], cwd=self.repo_root).strip()
            subprocess.run(
                ["git", "read-tree", tree_output],
                cwd=str(self.repo_root), check=True, capture_output=True, env=env_copy,
            )
            blob_result = subprocess.run(
                ["git", "hash-object", "-w", "--stdin"],
                cwd=str(self.repo_root), check=True, capture_output=True, text=True,
                input=content, env=env_copy,
            )
            blob_sha = blob_result.stdout.strip()
            subprocess.run(
                ["git", "update-index", "--add", "--cacheinfo", f"100644,{blob_sha},{path}"],
                cwd=str(self.repo_root), check=True, capture_output=True, env=env_copy,
            )
            tree_result = subprocess.run(
                ["git", "write-tree"],
                cwd=str(self.repo_root), check=True, capture_output=True, text=True, env=env_copy,
            )
            tree_sha = tree_result.stdout.strip()
            parent = git_run(["rev-parse", BRANCH_NAME], cwd=self.repo_root).strip()
            commit_result = subprocess.run(
                ["git", "commit-tree", tree_sha, "-p", parent, "-m", message],
                cwd=str(self.repo_root), check=True, capture_output=True, text=True,
            )
            commit_sha = commit_result.stdout.strip()
            git_run(["update-ref", f"refs/heads/{BRANCH_NAME}", commit_sha], cwd=self.repo_root)
        finally:
            if os.path.exists(tmp_index):
                os.unlink(tmp_index)

    def read_config(self) -> dict:
        content = self._read_file("survey.toml")
        return tomllib.loads(content)

    def write_config(self, config: dict) -> None:
        lines = _dict_to_toml(config)
        self._write_file("survey.toml", lines, "Update survey config")

    def write_session(self, session: Session) -> None:
        content = json.dumps(session.to_dict(), indent=2, ensure_ascii=False)
        path = f"sessions/{session.session_id}.json"
        self._write_file(path, content, f"Record session {session.session_id}")

    def read_session(self, session_id: str) -> Session:
        content = self._read_file(f"sessions/{session_id}.json")
        return Session.from_dict(json.loads(content))

    def list_sessions(self, since_days: int = 30) -> list[Session]:
        try:
            output = git_run(
                ["ls-tree", "--name-only", f"{BRANCH_NAME}:sessions/"],
                cwd=self.repo_root,
            )
        except subprocess.CalledProcessError:
            return []
        sessions = []
        for line in output.strip().splitlines():
            if not line.endswith(".json"):
                continue
            session_id = line.removesuffix(".json")
            sessions.append(self.read_session(session_id))
        return sessions


def _dict_to_toml(d: dict, prefix: str = "") -> str:
    lines: list[str] = []
    for key, value in d.items():
        if isinstance(value, dict):
            section = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
            lines.append(f"[{section}]")
            for k, v in value.items():
                if isinstance(v, str):
                    lines.append(f'{k} = "{v}"')
                else:
                    lines.append(f"{k} = {json.dumps(v)}")
            lines.append("")
        elif isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        else:
            lines.append(f"{key} = {json.dumps(value)}")
    return "\n".join(lines) + "\n"
