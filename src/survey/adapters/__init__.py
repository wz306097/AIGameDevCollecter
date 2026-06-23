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
        from survey.adapters.git_diff import GitDiffAdapter
        return GitDiffAdapter()
    return _REGISTRY[harness]()
