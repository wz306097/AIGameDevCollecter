from __future__ import annotations

from pathlib import Path


def ensure_store(repo_root: Path, name: str | None = None):
    """Return a BranchStore, creating the survey branch and hook if needed."""
    from survey.branch import BranchStore
    from survey.hooks import install_hooks

    store = BranchStore(repo_root)
    if not store.branch_exists():
        store.init_branch()
        config = store.read_config()
        config.setdefault("project", {})["name"] = name or repo_root.name
        store.write_config(config)
        install_hooks(repo_root)
    return store
