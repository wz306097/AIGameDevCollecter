from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from survey.git_ops import git_run
from survey.models import Session
from survey.report import generate_bench_report


BAD_CASE_CATEGORY_MAP = {
    "A1": "behavior_logic",
    "A2": "behavior_logic",
    "A3": "architecture",
    "B1": "intent_translation",
    "B2": "intent_translation",
    "B3": "intent_translation",
    "C1": "precise_edit",
    "C2": "precise_edit",
    "C3": "precise_edit",
}


def export_bench_testcases(
    repo_root: Path,
    sessions: list[Session],
    output_dir: Path,
    harness: str = "survey",
    include_clean: bool = False,
) -> list[Path]:
    """Write Survey bad cases as runnable AIGameDevBench testcase dirs."""
    report = generate_bench_report(sessions, harness=harness, include_clean=include_clean)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for record in report["testcases"]:
        tc_id = _testcase_id(record["testcase_id"])
        tc_dir = output_dir / tc_id
        tc_dir.mkdir(parents=True, exist_ok=True)

        session = record.get("survey_session", {})
        baseline_ref, repro_ref, resolution_error = _resolve_refs(repo_root, session.get("commits", []))
        category = _category_for_record(record)
        task = _task_for_record(record)

        spec = {
            "schema": "survey.bad_case.testcase.v1",
            "testcase_id": tc_id,
            "source_repo": str(repo_root),
            "baseline_ref": baseline_ref,
            "repro_ref": repro_ref,
            "baseline_resolution_error": resolution_error,
            "expected": _expected_for_record(record),
            "bench_record": record,
        }
        (tc_dir / "survey_bad_case.json").write_text(
            json.dumps(spec, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (tc_dir / "testcase.toml").write_text(
            _testcase_toml(tc_id, category, baseline_ref, str(repo_root), task, record),
            encoding="utf-8",
        )
        (tc_dir / "bad.diff").write_text(
            _bad_diff(repo_root, baseline_ref, repro_ref),
            encoding="utf-8",
        )
        written.append(tc_dir)

    return written


def write_bench_outputs(
    repo_root: Path,
    sessions: list[Session],
    report_path: Path | None = None,
    testcases_dir: Path | None = None,
    harness: str = "survey",
    include_clean: bool = False,
) -> dict:
    """Write the Bench report JSON and/or runnable testcase dirs."""
    report_data = generate_bench_report(
        sessions,
        harness=harness,
        include_clean=include_clean,
    )
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")
    if testcases_dir:
        export_bench_testcases(
            repo_root,
            sessions,
            testcases_dir,
            harness=harness,
            include_clean=include_clean,
        )
    return report_data


def _testcase_id(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", session_id).strip(".-")
    if not safe:
        safe = "bad-case"
    if not safe.startswith("survey-"):
        safe = f"survey-{safe}"
    return safe[:100]


def _category_for_record(record: dict[str, Any]) -> str:
    bad_type = str(record.get("survey_session", {}).get("bad_case_type") or "")
    return BAD_CASE_CATEGORY_MAP.get(bad_type, "behavior_logic")


def _task_for_record(record: dict[str, Any]) -> str:
    ctx = record.get("ai_agent_context", {})
    turns = ctx.get("turns", []) if isinstance(ctx, dict) else []
    user_turns = [
        str(turn.get("agent_input", "")).strip()
        for turn in turns
        if isinstance(turn, dict) and str(turn.get("agent_input", "")).strip()
    ]
    if user_turns:
        task = user_turns[0]
        if len(user_turns) > 1:
            followups = "\n".join(f"- {line}" for line in user_turns[1:])
            task += "\n\nFollow-up user turns from the original session:\n" + followups
    else:
        session = record.get("survey_session", {})
        files = session.get("changed_files", [])
        notes = session.get("notes") or record.get("verifier_result", {}).get("error") or ""
        file_text = ", ".join(str(f) for f in files[:8]) if isinstance(files, list) else ""
        task = "Complete the original Survey bad-case task"
        if file_text:
            task += f" touching the relevant files: {file_text}"
        if notes:
            task += f". Original failure notes: {notes}"

    session = record.get("survey_session", {})
    bad_type = session.get("bad_case_type") or "unclassified"
    notes = session.get("notes") or ""
    if notes:
        task += f"\n\nRegression target: avoid the original Survey bad case ({bad_type}): {notes}"
    else:
        task += f"\n\nRegression target: avoid the original Survey bad case ({bad_type})."
    return task


def _expected_for_record(record: dict[str, Any]) -> dict[str, Any]:
    session = record.get("survey_session", {})
    verification = session.get("verification") or {}
    outcome = session.get("outcome") or {}
    changed_files = session.get("changed_files", [])
    relevant_files = [
        str(path).replace("\\", "/")
        for path in changed_files
        if path and not _is_generated_file(str(path))
    ] if isinstance(changed_files, list) else []
    return {
        "bad_case_type": session.get("bad_case_type"),
        "notes": session.get("notes"),
        "original_l0_pass": verification.get("l0_pass"),
        "original_l1_pass": verification.get("l1_pass"),
        "original_l0_details": verification.get("l0_details", []),
        "original_l1_details": verification.get("l1_details", []),
        "original_human_intervention_ratio": outcome.get("human_intervention_ratio"),
        "original_rounds_to_resolution": outcome.get("rounds_to_resolution"),
        "must_change_one_of": relevant_files,
        "minimum_changed_files": 1,
    }


def _is_generated_file(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return (
        normalized.startswith(".godot/")
        or normalized.endswith(".uid")
        or normalized.endswith(".import")
        or "/.godot/" in normalized
    )


def _resolve_refs(repo_root: Path, commits: Any) -> tuple[str, str | None, str | None]:
    commit_list = [str(c) for c in commits if c] if isinstance(commits, list) else []
    if commit_list:
        newest = commit_list[0]
        oldest = commit_list[-1]
        try:
            repro_ref = git_run(["rev-parse", newest], cwd=repo_root).strip()
        except Exception as exc:  # pragma: no cover - exact git exception varies by platform
            repro_ref = newest
            return _head_ref(repo_root), repro_ref, f"could not resolve repro commit {newest}: {exc}"

        try:
            baseline_ref = git_run(["rev-parse", f"{oldest}^"], cwd=repo_root).strip()
            return baseline_ref, repro_ref, None
        except Exception:
            try:
                baseline_ref = git_run(["rev-parse", oldest], cwd=repo_root).strip()
                return baseline_ref, repro_ref, f"commit {oldest} has no resolvable parent"
            except Exception as exc:  # pragma: no cover - exact git exception varies by platform
                return _head_ref(repo_root), repro_ref, f"could not resolve baseline for {oldest}: {exc}"

    return _head_ref(repo_root), None, "session has no commits; using HEAD as baseline"


def _head_ref(repo_root: Path) -> str:
    try:
        return git_run(["rev-parse", "HEAD"], cwd=repo_root).strip()
    except Exception:
        return "HEAD"


def _bad_diff(repo_root: Path, baseline_ref: str, repro_ref: str | None) -> str:
    if not repro_ref or not baseline_ref:
        return ""
    try:
        return git_run(["diff", "--binary", f"{baseline_ref}..{repro_ref}"], cwd=repo_root)
    except Exception:
        return ""


def _testcase_toml(
    tc_id: str,
    category: str,
    baseline_ref: str,
    source_repo: str,
    task: str,
    record: dict[str, Any],
) -> str:
    session = record.get("survey_session", {})
    ai_ctx = record.get("ai_agent_context", {})
    lines = [
        "[testcase]",
        f"id = {_toml_string(tc_id)}",
        f"category = {_toml_string(category)}",
        "source_kind = \"git\"",
        f"baseline_ref = {_toml_string(baseline_ref)}",
        f"source_repo = {_toml_string(source_repo)}",
        f"task = {_toml_string(task)}",
        "",
        "[verifier]",
        "type = \"survey_bad_case\"",
        "entry = \"survey_bad_case.json\"",
        "",
        "[scoring]",
        "mode = \"checkpoints\"",
        "",
        "[provenance]",
        "source = \"survey\"",
        f"source_session = {_toml_string(session.get('session_id', record.get('testcase_id', '')))}",
        f"bad_case_type = {_toml_string(session.get('bad_case_type') or 'unclassified')}",
        f"captured_harness = {_toml_string(session.get('harness') or record.get('harness', ''))}",
        f"transcript_session_id = {_toml_string(ai_ctx.get('transcript_session_id') or '')}",
        "context_file = \"survey_bad_case.json\"",
        "bad_diff = \"bad.diff\"",
        "",
    ]
    return "\n".join(lines)


def _toml_string(value: Any) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)
