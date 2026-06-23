from __future__ import annotations

from pathlib import Path

import click

from survey.git_ops import get_repo_root


def _ensure_store(repo_root: Path, name: str | None = None):
    """Return a BranchStore, auto-initializing the survey branch if missing.

    Makes `collect`/`watch`/`report` work with zero prior setup —
    `cd <repo> && survey watch` is the entire onboarding.
    """
    from survey.branch import BranchStore
    from survey.hooks import install_hooks as do_install_hooks

    store = BranchStore(repo_root)
    if not store.branch_exists():
        store.init_branch()
        config = store.read_config()
        config.setdefault("project", {})["name"] = name or repo_root.name
        store.write_config(config)
        do_install_hooks(repo_root)
    return store


def _parse_interval(value: str) -> int:
    """Parse '30m', '2h', '45s', or a bare integer (seconds) into seconds."""
    value = value.strip().lower()
    if value.endswith("h"):
        return int(float(value[:-1]) * 3600)
    if value.endswith("m"):
        return int(float(value[:-1]) * 60)
    if value.endswith("s"):
        return int(float(value[:-1]))
    return int(value)


@click.group()
@click.version_option()
def main():
    """Survey: AI game development evaluation system."""
    pass


@main.command()
@click.option("--name", default=None, help="Project name (defaults to repo folder name)")
@click.option("--install-hooks/--no-hooks", default=True, help="Install post-commit hook")
def init(name: str | None, install_hooks: bool):
    """Initialize survey branch in current repo."""
    from survey.branch import BranchStore
    from survey.hooks import install_hooks as do_install_hooks

    repo_root = get_repo_root(Path.cwd())
    name = name or repo_root.name
    store = BranchStore(repo_root)
    store.init_branch()

    config = store.read_config()
    config.setdefault("project", {})["name"] = name
    store.write_config(config)

    if install_hooks:
        do_install_hooks(repo_root)
        click.echo(f"Initialized survey branch with post-commit hook for '{name}'.")
    else:
        click.echo(f"Initialized survey branch for '{name}'.")


@main.group()
def config():
    """Manage survey configuration."""
    pass


@config.command("show")
def config_show():
    """Show current survey configuration."""
    from survey.branch import BranchStore

    repo_root = get_repo_root(Path.cwd())
    store = BranchStore(repo_root)
    if not store.branch_exists():
        click.echo("Survey not initialized. Run 'survey init' first.")
        return
    cfg = store.read_config()
    import json
    click.echo(json.dumps(cfg, indent=2, ensure_ascii=False))


@main.command()
@click.option("--intent", "-i", default=None, help="Task intent description")
@click.option("--session", "-s", default=None, help="Session ID to annotate (default: most recent)")
def annotate(intent: str | None, session: str | None):
    """Add metadata to a session."""
    from survey.branch import BranchStore

    repo_root = get_repo_root(Path.cwd())
    store = BranchStore(repo_root)
    sessions = store.list_sessions()
    if not sessions:
        click.echo("No sessions found.")
        return

    target = None
    if session:
        for s in sessions:
            if s.session_id == session:
                target = s
                break
    else:
        target = sessions[-1]

    if not target:
        click.echo(f"Session '{session}' not found.")
        return

    if intent:
        if not target.prompts:
            from survey.models import Turn
            target.prompts.append(Turn(turn=0, user_message=intent, assistant_summary="(annotated)", tool_calls=[]))
        target.system_context["annotated_intent"] = intent

    store.write_session(target)
    click.echo(f"Annotated session {target.session_id}.")


@main.command()
@click.option("--pending", is_flag=True, help="List sessions awaiting classification")
@click.option("--last", is_flag=True, help="Tag most recent session")
@click.option("--type", "bad_type", default=None, help="Bad case type (A1-C3)")
@click.option("--notes", default=None, help="Additional notes")
@click.argument("session_id", required=False)
def tag(pending: bool, last: bool, bad_type: str | None, notes: str | None, session_id: str | None):
    """Classify sessions as bad cases."""
    from survey.branch import BranchStore
    from survey.badcase import detect_bad_case

    repo_root = get_repo_root(Path.cwd())
    store = BranchStore(repo_root)
    sessions = store.list_sessions()

    if pending:
        pending_sessions = []
        for s in sessions:
            if s.tag and s.tag.auto_detected and not s.tag.bad_case_type:
                pending_sessions.append(s)
            elif not s.tag:
                tag_info = detect_bad_case(s)
                if tag_info:
                    s.tag = tag_info
                    store.write_session(s)
                    pending_sessions.append(s)

        if not pending_sessions:
            click.echo("No sessions pending classification.")
            return

        for i, s in enumerate(pending_sessions, 1):
            click.echo(f"\n[{i}] {s.session_id} (auto_detected: {s.tag.notes})")
            if s.tag.suggested_type:
                click.echo(f"    Suggested: Type {s.tag.suggested_type}")
            if s.changed_files:
                click.echo(f"    Files: {', '.join(s.changed_files[:5])}")
        return

    target = None
    if session_id:
        for s in sessions:
            if s.session_id == session_id:
                target = s
                break
    elif last and sessions:
        target = sessions[-1]

    if not target:
        click.echo("No session found. Specify a session ID or use --last.")
        return

    if bad_type:
        from survey.models import TagInfo
        if not target.tag:
            target.tag = TagInfo()
        target.tag.bad_case_type = bad_type
        if notes:
            target.tag.notes = notes
        store.write_session(target)
        click.echo(f"Tagged {target.session_id} as {bad_type}.")


@main.command()
@click.argument("session_id", required=False)
@click.option("--last", is_flag=True, help="Verify most recent session")
@click.option("--quiet", is_flag=True, help="Suppress output except errors")
def verify(session_id: str | None, last: bool, quiet: bool):
    """Run L0/L1 validation on a session."""
    from survey.branch import BranchStore
    from survey.validation import run_validation
    from survey.config import get_merged_config

    repo_root = get_repo_root(Path.cwd())
    store = BranchStore(repo_root)
    sessions = store.list_sessions()

    target = None
    if session_id:
        for s in sessions:
            if s.session_id == session_id:
                target = s
                break
    elif last and sessions:
        target = sessions[-1]

    if not target:
        if not quiet:
            click.echo("No session found.")
        return

    config = get_merged_config(repo_root)
    result = run_validation(repo_root, target.changed_files, config)
    target.verification = result
    store.write_session(target)

    if not quiet:
        click.echo(f"survey: L0 {'pass' if result.l0_pass else 'FAIL'}, L1 {'pass' if result.l1_pass else 'FAIL'}")
        for detail in result.l0_details + result.l1_details:
            click.echo(f"  {detail}")


@main.command()
@click.option("--period", default="30d", help="Time period (e.g., 7d, 30d)")
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
def report(period: str, fmt: str):
    """Generate evaluation report."""
    from survey.report import generate_report

    repo_root = get_repo_root(Path.cwd())
    store = _ensure_store(repo_root)
    sessions = store.list_sessions()

    if fmt == "md":
        md = generate_report(sessions, period)
        click.echo(md)
    else:
        import json
        click.echo(json.dumps([s.to_dict() for s in sessions], indent=2, ensure_ascii=False))


def _collect_once(repo_root: Path, since: str, harness: str | None) -> tuple[int, int]:
    """Collect sessions, compute metrics, auto-detect bad cases, persist.

    Returns (sessions_recorded, bad_cases_flagged).
    """
    from survey.adapters import get_adapter
    from survey.adapters.git_diff import GitDiffAdapter
    from survey.metrics import compute_metrics
    from survey.badcase import detect_bad_case
    from survey.config import get_merged_config

    store = _ensure_store(repo_root)
    config = get_merged_config(repo_root)

    adapter = get_adapter(harness or "unknown")
    if not isinstance(adapter, GitDiffAdapter):
        raise click.ClickException(
            f"Transcript-based collection for '{harness}' is not yet supported."
        )

    sessions = adapter.infer_sessions(repo_root, since=since, until="now")

    recorded = 0
    flagged = 0
    for session in sessions:
        session.outcome = compute_metrics(session, repo_root=repo_root, config=config)
        tag_info = detect_bad_case(session)
        if tag_info:
            session.tag = tag_info
            flagged += 1
        store.write_session(session)
        recorded += 1

    return recorded, flagged


@main.command()
@click.option("--since", default="7d", help="Collect sessions from the last N days")
@click.option("--harness", default=None, help="Harness to use for transcript parsing")
def collect(since: str, harness: str | None):
    """Collect and assemble sessions from harness transcripts and git history."""
    repo_root = get_repo_root(Path.cwd())
    recorded, flagged = _collect_once(repo_root, since, harness)
    click.echo(f"Collected {recorded} session(s); {flagged} flagged as bad case(s).")


@main.command()
@click.option("--interval", default="30m", help="Time between passes (e.g. 45s, 30m, 2h)")
@click.option("--since", default="7d", help="Collect sessions from the last N days")
@click.option("--harness", default=None, help="Harness to use for transcript parsing")
@click.option("--once", is_flag=True, help="Run a single pass and exit")
def watch(interval: str, since: str, harness: str | None, once: bool):
    """Periodically collect sessions and flag bad cases (built-in scheduler)."""
    import time

    repo_root = get_repo_root(Path.cwd())
    seconds = _parse_interval(interval)

    def _pass():
        recorded, flagged = _collect_once(repo_root, since, harness)
        click.echo(f"[watch] collected {recorded} session(s); {flagged} bad case(s).")

    if once:
        _pass()
        return

    click.echo(f"[watch] every {interval} (Ctrl-C to stop). Watching {repo_root}.")
    try:
        while True:
            _pass()
            time.sleep(seconds)
    except KeyboardInterrupt:
        click.echo("\n[watch] stopped.")
