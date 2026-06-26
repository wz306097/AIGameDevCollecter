from __future__ import annotations

import json
from pathlib import Path

import click

from survey.git_ops import get_repo_root
from survey.storage import ensure_store
from survey.transcripts import import_transcripts_once, merge_transcript_context_into_session


def _parse_interval(value: str) -> int:
    """Parse '30m', '2h', '45s', or a bare integer into seconds."""
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
    """Initialize the survey storage branch in the current repo."""
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
    click.echo(json.dumps(store.read_config(), indent=2, ensure_ascii=False))


@main.command()
@click.option("--intent", "-i", default=None, help="Task intent description")
@click.option("--session", "-s", default=None, help="Session ID to annotate (default: most recent)")
def annotate(intent: str | None, session: str | None):
    """Add metadata to a session."""
    from survey.branch import BranchStore
    from survey.models import Turn

    repo_root = get_repo_root(Path.cwd())
    store = BranchStore(repo_root)
    sessions = store.list_sessions()
    if not sessions:
        click.echo("No sessions found.")
        return

    target = _select_session(sessions, session, last=session is None)
    if not target:
        click.echo(f"Session '{session}' not found.")
        return

    if intent:
        if not target.prompts:
            target.prompts.append(Turn(turn=0, user_message=intent, assistant_summary="(annotated)", tool_calls=[]))
        target.system_context["annotated_intent"] = intent

    store.write_session(target)
    click.echo(f"Annotated session {target.session_id}.")


@main.command()
@click.option("--pending", is_flag=True, help="List sessions awaiting classification")
@click.option("--last", is_flag=True, help="Tag most recent session")
@click.option("--type", "bad_type", default=None, help="Bad case type (A1-C3)")
@click.option("--notes", default=None, help="Additional notes")
@click.option("--with-transcript/--no-transcript", default=True, help="Auto-merge matching agent transcript context")
@click.option("--harness", default=None, help="Transcript harness for --with-transcript. Omit to auto-discover.")
@click.option("--path", "transcript_path", default=None, type=click.Path(exists=True), help="Transcript file or directory for --with-transcript")
@click.option("--bench-report", default=None, type=click.Path(), help="Refresh an AIGameDevBench-compatible report after tagging")
@click.option("--bench-harness", default="survey", help="Harness label for --bench-report")
@click.option("--bench-testcases-dir", default=None, type=click.Path(), help="Refresh AIGameDevBench testcase dirs after tagging")
@click.option("--include-clean", is_flag=True, help="Include clean sessions in Bench outputs")
@click.argument("session_id", required=False)
def tag(
    pending: bool,
    last: bool,
    bad_type: str | None,
    notes: str | None,
    with_transcript: bool,
    harness: str | None,
    transcript_path: str | None,
    bench_report: str | None,
    bench_harness: str,
    bench_testcases_dir: str | None,
    include_clean: bool,
    session_id: str | None,
):
    """Classify sessions as bad cases."""
    from survey.badcase import detect_bad_case
    from survey.branch import BranchStore
    from survey.models import TagInfo

    repo_root = get_repo_root(Path.cwd())
    store = BranchStore(repo_root)
    sessions = store.list_sessions()

    if pending:
        _print_pending_sessions(sessions, store, detect_bad_case)
        return

    target = _select_session(sessions, session_id, last=last)
    if not target:
        click.echo("No session found. Specify a session ID or use --last.")
        return

    if not bad_type:
        click.echo("No bad case type supplied. Use --type A1-C3.")
        return

    if not target.tag:
        target.tag = TagInfo()
    target.tag.bad_case_type = bad_type
    if notes:
        target.tag.notes = notes

    merged = 0
    skipped = 0
    if with_transcript:
        target, merged, skipped = merge_transcript_context_into_session(
            repo_root,
            target,
            harness,
            Path(transcript_path) if transcript_path else None,
        )

    store.write_session(target)
    _refresh_bench_outputs(repo_root, bench_report, bench_testcases_dir, bench_harness, include_clean)

    message = f"Tagged {target.session_id} as {bad_type}."
    if with_transcript:
        message += f" Merged {merged} transcript(s)."
        if skipped:
            message += f" Skipped {skipped} unrelated/non-transcript file(s)."
    if bench_report:
        message += f" Refreshed {bench_report}."
    if bench_testcases_dir:
        message += f" Refreshed testcases in {bench_testcases_dir}."
    click.echo(message)


@main.command()
@click.argument("session_id", required=False)
@click.option("--last", is_flag=True, help="Verify most recent session")
@click.option("--quiet", is_flag=True, help="Suppress output except errors")
def verify(session_id: str | None, last: bool, quiet: bool):
    """Run L0/L1 validation on a session."""
    from survey.branch import BranchStore
    from survey.config import get_merged_config
    from survey.validation import run_validation

    repo_root = get_repo_root(Path.cwd())
    store = BranchStore(repo_root)
    target = _select_session(store.list_sessions(), session_id, last=last)
    if not target:
        if not quiet:
            click.echo("No session found.")
        return

    result = run_validation(repo_root, target.changed_files, get_merged_config(repo_root))
    target.verification = result
    store.write_session(target)

    if not quiet:
        click.echo(f"survey: L0 {'pass' if result.l0_pass else 'FAIL'}, L1 {'pass' if result.l1_pass else 'FAIL'}")
        for detail in result.l0_details + result.l1_details:
            click.echo(f"  {detail}")


@main.command()
@click.option("--period", default="30d", help="Time period label shown in the report")
@click.option("--format", "fmt", type=click.Choice(["md", "json"]), default="md")
def report(period: str, fmt: str):
    """Generate a Survey summary report."""
    from survey.report import generate_report

    repo_root = get_repo_root(Path.cwd())
    store = ensure_store(repo_root)
    sessions = store.list_sessions()

    if fmt == "md":
        click.echo(generate_report(sessions, period))
    else:
        click.echo(json.dumps([s.to_dict() for s in sessions], indent=2, ensure_ascii=False))


@main.command("export-bench")
@click.option("--output", "-o", required=True, type=click.Path(), help="Write AIGameDevBench-compatible JSON here")
@click.option("--harness", default="survey", help="Harness label shown in AIGameDevBench")
@click.option("--testcases-dir", default=None, type=click.Path(), help="Also write bad cases as AIGameDevBench testcase dirs")
@click.option("--with-transcript/--no-transcript", default=True, help="Auto-import matching Claude Code/Codex transcript context before export")
@click.option("--transcript-harness", default=None, help="Transcript harness for --with-transcript. Omit to auto-discover.")
@click.option("--transcript-path", default=None, type=click.Path(exists=True), help="Transcript file or directory for --with-transcript")
@click.option("--include-clean", is_flag=True, help="Include non-bad-case sessions as passing rows")
def export_bench(
    output: str,
    harness: str,
    testcases_dir: str | None,
    with_transcript: bool,
    transcript_harness: str | None,
    transcript_path: str | None,
    include_clean: bool,
):
    """Export Survey bad cases as AIGameDevBench report/testcase artifacts."""
    repo_root = get_repo_root(Path.cwd())
    if with_transcript:
        import_transcripts_once(
            repo_root,
            transcript_harness,
            Path(transcript_path) if transcript_path else None,
        )
    store = ensure_store(repo_root)
    report_data = _refresh_bench_outputs(
        repo_root,
        output,
        testcases_dir,
        harness,
        include_clean,
        sessions=store.list_sessions(),
    )
    click.echo(f"Exported {report_data['count']} survey row(s) to {Path(output)}.")
    if testcases_dir:
        click.echo(f"Exported {report_data['count']} survey testcase(s) to {Path(testcases_dir)}.")


@main.command("import-transcripts")
@click.option("--harness", default=None, help="Transcript harness. Omit to auto-discover claude-code and codex transcripts.")
@click.option("--path", "transcript_path", default=None, type=click.Path(exists=True), help="Transcript file or directory; auto-discovered when omitted")
@click.option("--bench-report", default=None, type=click.Path(), help="Refresh an AIGameDevBench-compatible report after import")
@click.option("--bench-harness", default="survey", help="Harness label for --bench-report")
@click.option("--bench-testcases-dir", default=None, type=click.Path(), help="Refresh AIGameDevBench testcase dirs after import")
@click.option("--include-clean", is_flag=True, help="Include clean sessions in Bench outputs")
def import_transcripts(
    harness: str | None,
    transcript_path: str,
    bench_report: str | None,
    bench_harness: str,
    bench_testcases_dir: str | None,
    include_clean: bool,
):
    """Import agent transcript context into Survey sessions."""
    repo_root = get_repo_root(Path.cwd())
    imported, flagged, skipped = import_transcripts_once(
        repo_root,
        harness,
        Path(transcript_path) if transcript_path else None,
    )
    _refresh_bench_outputs(repo_root, bench_report, bench_testcases_dir, bench_harness, include_clean)

    message = f"Imported {imported} transcript(s); {flagged} bad case(s)."
    if skipped:
        message += f" Skipped {skipped} non-transcript file(s)."
    if bench_testcases_dir:
        message += f" Refreshed testcases in {bench_testcases_dir}."
    click.echo(message)


@main.command()
@click.option("--since", default="7d", help="Collect sessions from the last N days")
@click.option("--harness", default=None, help="Harness to use for transcript parsing")
def collect(since: str, harness: str | None):
    """Collect and assemble sessions from git history."""
    repo_root = get_repo_root(Path.cwd())
    recorded, flagged = _collect_once(repo_root, since, harness)
    click.echo(f"Collected {recorded} session(s); {flagged} flagged as bad case(s).")


@main.command()
@click.option("--interval", default="30m", help="Time between passes (e.g. 45s, 30m, 2h)")
@click.option("--since", default="7d", help="Collect sessions from the last N days")
@click.option("--harness", default=None, help="Harness to use for transcript parsing")
@click.option("--once", is_flag=True, help="Run a single pass and exit")
@click.option("--bench-report", default=None, type=click.Path(), help="Continuously refresh an AIGameDevBench-compatible report JSON")
@click.option("--bench-harness", default="survey", help="Harness label for --bench-report")
@click.option("--bench-testcases-dir", default=None, type=click.Path(), help="Continuously refresh AIGameDevBench testcase dirs")
@click.option("--include-clean", is_flag=True, help="Include clean sessions in Bench outputs")
def watch(
    interval: str,
    since: str,
    harness: str | None,
    once: bool,
    bench_report: str | None,
    bench_harness: str,
    bench_testcases_dir: str | None,
    include_clean: bool,
):
    """Periodically collect sessions and flag bad cases."""
    import time

    repo_root = get_repo_root(Path.cwd())
    seconds = _parse_interval(interval)

    def _pass():
        recorded, flagged = _collect_once(repo_root, since, harness)
        _refresh_bench_outputs(repo_root, bench_report, bench_testcases_dir, bench_harness, include_clean)
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


def _collect_once(repo_root: Path, since: str, harness: str | None) -> tuple[int, int]:
    """Collect sessions, compute metrics, auto-detect bad cases, and persist them."""
    from survey.adapters import get_adapter
    from survey.adapters.git_diff import GitDiffAdapter
    from survey.badcase import detect_bad_case
    from survey.config import get_merged_config
    from survey.metrics import compute_metrics

    store = ensure_store(repo_root)
    config = get_merged_config(repo_root)

    adapter = get_adapter(harness or "unknown")
    if not isinstance(adapter, GitDiffAdapter):
        raise click.ClickException(
            f"Transcript-based collection for '{harness}' is not supported by collect/watch. "
            "Use 'survey import-transcripts' instead."
        )

    recorded = 0
    flagged = 0
    for session in adapter.infer_sessions(repo_root, since=since, until="now"):
        session.outcome = compute_metrics(session, repo_root=repo_root, config=config)
        tag_info = detect_bad_case(session)
        if tag_info:
            session.tag = tag_info
            flagged += 1
        store.write_session(session)
        recorded += 1
    return recorded, flagged


def _refresh_bench_outputs(
    repo_root: Path,
    report_path: str | None,
    testcases_dir: str | None,
    harness: str,
    include_clean: bool,
    sessions=None,
):
    if not report_path and not testcases_dir:
        return None
    from survey.bench_testcases import write_bench_outputs
    from survey.branch import BranchStore

    if sessions is None:
        sessions = BranchStore(repo_root).list_sessions()
    return write_bench_outputs(
        repo_root,
        sessions,
        report_path=Path(report_path) if report_path else None,
        testcases_dir=Path(testcases_dir) if testcases_dir else None,
        harness=harness,
        include_clean=include_clean,
    )


def _select_session(sessions, session_id: str | None, last: bool = False):
    if session_id:
        for session in sessions:
            if session.session_id == session_id:
                return session
        return None
    if last and sessions:
        return sessions[-1]
    return None


def _print_pending_sessions(sessions, store, detect_bad_case) -> None:
    pending_sessions = []
    for session in sessions:
        if session.tag and session.tag.auto_detected and not session.tag.bad_case_type:
            pending_sessions.append(session)
        elif not session.tag:
            tag_info = detect_bad_case(session)
            if tag_info:
                session.tag = tag_info
                store.write_session(session)
                pending_sessions.append(session)

    if not pending_sessions:
        click.echo("No sessions pending classification.")
        return

    for i, session in enumerate(pending_sessions, 1):
        click.echo(f"\n[{i}] {session.session_id} (auto_detected: {session.tag.notes})")
        if session.tag.suggested_type:
            click.echo(f"    Suggested: Type {session.tag.suggested_type}")
        if session.changed_files:
            click.echo(f"    Files: {', '.join(session.changed_files[:5])}")
