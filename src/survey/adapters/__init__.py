from __future__ import annotations

from survey.adapters.base import HarnessAdapter


_REGISTRY: dict[str, type] = {}


def register(name: str):
    def decorator(cls):
        _REGISTRY[name] = cls
        return cls
    return decorator


def get_adapter(harness: str) -> HarnessAdapter:
    if harness not in _REGISTRY:
        if harness == "claude-code":
            from survey.adapters.claude_code import ClaudeCodeAdapter
            return ClaudeCodeAdapter()
        if harness == "codex":
            from survey.adapters.codex import CodexAdapter
            return CodexAdapter()
        from survey.adapters.git_diff import GitDiffAdapter
        return GitDiffAdapter()
    return _REGISTRY[harness]()
