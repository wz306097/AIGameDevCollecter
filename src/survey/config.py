from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


DEFAULT_GLOBAL_CONFIG: dict = {
    "godot": {
        "binary": "godot",
        "headless_args": ["--headless", "--quit-after", "5"],
    },
    "transcript_sources": {
        "claude-code": "~/.claude/projects/*/sessions/",
        "codex": "~/.codex/sessions/**/*.jsonl",
        "cursor": "~/.cursor-tutor/state/logs/",
        "copilot": "",
    },
    "llm": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "api_key_env": "ANTHROPIC_API_KEY",
    },
    "git": {
        # A commit counts as AI-authored when its message has a
        # `Co-Authored-By:` trailer matching any of these (case-insensitive
        # substring). Used by metrics to split AI vs human line counts.
        "ai_authors": ["claude", "cursor", "copilot", "gpt", "codex", "noreply@anthropic.com"],
    },
}

DEFAULT_REPO_CONFIG: dict = {
    "project": {
        "name": "",
        "engine": "godot",
        "engine_version": "4.3",
        "main_scene": "scenes/main.tscn",
    },
    "harnesses": [],
    "validation": {
        "test_scenes": ["scenes/**/*.tscn"],
        "exclude_paths": ["addons/**", ".import/**"],
        "l2_timeout": 30,
        "l2_max_frames": 300,
    },
    "conventions": {
        "script_naming": "snake_case",
        "scene_naming": "PascalCase",
        "signal_naming": "snake_case",
        "node_structure_patterns": [],
        "banned_patterns": [],
    },
    "labels": {
        "types": ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"],
        "custom_tags": [],
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_global_config(config_dir: Path | None = None) -> dict:
    if config_dir is None:
        config_dir = Path.home() / ".config" / "survey"
    config_file = config_dir / "config.toml"
    if config_file.exists():
        with open(config_file, "rb") as f:
            user_config = tomllib.load(f)
        return _deep_merge(DEFAULT_GLOBAL_CONFIG, user_config)
    return DEFAULT_GLOBAL_CONFIG.copy()


def load_repo_config(toml_path: Path) -> dict:
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def get_merged_config(repo_root: Path) -> dict:
    from survey.branch import BranchStore

    global_config = load_global_config()
    store = BranchStore(repo_root)
    if store.branch_exists():
        repo_config = store.read_config()
    else:
        repo_config = DEFAULT_REPO_CONFIG.copy()
    return {"global": global_config, **repo_config}
