from __future__ import annotations

from collections import defaultdict

from survey.models import Session


def generate_report(sessions: list[Session], period_label: str) -> str:
    lines: list[str] = []
    lines.append(f"## Survey Report ({period_label})")
    lines.append("")

    bad_cases = [s for s in sessions if _is_bad_case(s)]

    lines.append("### Summary")
    lines.append(f"Total sessions: {len(sessions)} | Bad cases: {len(bad_cases)} ({_pct(len(bad_cases), len(sessions))})")
    lines.append("")

    if not sessions:
        return "\n".join(lines)

    by_config: dict[str, list[Session]] = defaultdict(list)
    for s in sessions:
        config_id = s.config.get("id", s.harness)
        by_config[config_id].append(s)

    lines.append("### Harness Comparison")
    lines.append("")
    lines.append("| Config | Sessions | L0 Pass | L1 Pass | First Pass | Avg Rounds | Avg Human % | Avg Tokens |")
    lines.append("|--------|----------|---------|---------|------------|------------|-------------|------------|")

    for config_id, group in sorted(by_config.items()):
        n = len(group)
        l0 = sum(1 for s in group if s.verification and s.verification.l0_pass)
        l1 = sum(1 for s in group if s.verification and s.verification.l1_pass)
        fp = sum(1 for s in group if s.outcome and s.outcome.first_pass_success)
        rounds = [s.outcome.rounds_to_resolution for s in group if s.outcome]
        avg_rounds = sum(rounds) / len(rounds) if rounds else 0
        human_ratios = [s.outcome.human_intervention_ratio for s in group if s.outcome]
        avg_human = sum(human_ratios) / len(human_ratios) if human_ratios else 0
        tokens = [s.outcome.token_cost for s in group if s.outcome]
        avg_tokens = sum(tokens) / len(tokens) if tokens else 0

        lines.append(
            f"| {config_id} | {n} | {_pct(l0, n)} | {_pct(l1, n)} | {_pct(fp, n)} "
            f"| {avg_rounds:.1f} | {avg_human:.0%} | {avg_tokens:.0f} |"
        )
    lines.append("")

    if bad_cases:
        lines.append("### Bad Case Distribution")
        lines.append("")
        type_counts: dict[str, int] = defaultdict(int)
        for s in bad_cases:
            type_counts[_bad_case_type(s)] += 1

        lines.append("| Type | Count |")
        lines.append("|------|-------|")
        for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| {t} | {c} |")
        lines.append("")

        lines.append("### Notable Bad Cases")
        lines.append("")
        for i, s in enumerate(bad_cases[:5], 1):
            intent = ""
            if s.prompts:
                intent = s.prompts[0].user_message[:60]
            notes = s.tag.notes if s.tag and s.tag.notes else ""
            lines.append(f"{i}. **[{_bad_case_type(s)}] {s.session_id}** - {s.harness}")
            if intent:
                lines.append(f'   Task: "{intent}"')
            if notes:
                lines.append(f"   Notes: {notes}")
            lines.append("")

    return "\n".join(lines)


def generate_bench_report(
    sessions: list[Session],
    harness: str = "survey",
    include_clean: bool = False,
) -> dict:
    """Return an AIGameDevBench-compatible JSON report.

    AIGameDevBench already loads reports shaped as:
    {"harness", "count", "mean_score", "testcases": [...]}. Treat every survey
    session as a row: bad cases score 0, clean sessions score 1. By default only
    bad cases are exported so the Bench dashboard stays focused on regressions.
    """
    prepared = _attach_available_transcript_context(sessions)
    records = [
        _bench_record(s)
        for s in prepared
        if include_clean or _is_bad_case(s)
    ]
    count = len(records)
    mean = sum(r["score"] for r in records) / count if count else 0.0
    return {
        "harness": harness,
        "count": count,
        "mean_score": mean,
        "testcases": records,
    }


def _attach_available_transcript_context(sessions: list[Session]) -> list[Session]:
    transcript_sessions = [
        s for s in sessions
        if (s.prompts or s.system_context.get("transcript_format"))
        and not _is_bad_case(s)
    ]
    if not transcript_sessions:
        return sessions

    prepared: list[Session] = []
    for session in sessions:
        if not _is_bad_case(session) or session.prompts:
            prepared.append(session)
            continue
        context = _find_context_session(session, transcript_sessions)
        prepared.append(_merge_context_for_report(session, context) if context else session)
    return prepared


def _find_context_session(target: Session, candidates: list[Session]) -> Session | None:
    target_commits = set(target.commits)
    if target_commits:
        for candidate in candidates:
            turn_commits = candidate.system_context.get("turn_commits", {})
            if isinstance(turn_commits, dict):
                for commits in turn_commits.values():
                    if isinstance(commits, list) and target_commits & set(str(c) for c in commits):
                        return candidate
            if target_commits & set(candidate.commits):
                return candidate

    target_files = set(target.changed_files)
    if not target_files:
        return None

    best: tuple[float, Session | None] = (0.0, None)
    for candidate in candidates:
        candidate_files = set(candidate.changed_files)
        if not candidate_files:
            turn_files = candidate.system_context.get("turn_files", {})
            if isinstance(turn_files, dict):
                for files in turn_files.values():
                    if isinstance(files, list):
                        candidate_files.update(str(f) for f in files)
        if not candidate_files:
            continue
        score = len(target_files & candidate_files) / len(target_files | candidate_files)
        if score > best[0]:
            best = (score, candidate)
    return best[1] if best[0] >= 0.2 else None


def _merge_context_for_report(target: Session, context: Session) -> Session:
    from copy import deepcopy

    merged = deepcopy(target)
    narrowed = _narrow_context_for_report(context, target)
    merged.prompts = narrowed.prompts or merged.prompts
    merged.system_context.update(narrowed.system_context)
    merged.harness = narrowed.harness or merged.harness
    merged.changed_files = sorted(set(merged.changed_files) | set(narrowed.changed_files))
    merged.timestamps.update({k: v for k, v in narrowed.timestamps.items() if v})
    merged.system_context["transcript_session_id"] = narrowed.session_id
    merged.system_context.setdefault("transcript_match_confidence", "high")
    return merged


def _narrow_context_for_report(source: Session, target: Session) -> Session:
    turn_commits = source.system_context.get("turn_commits", {})
    if not isinstance(turn_commits, dict) or not target.commits:
        return source

    target_commits = set(target.commits)
    matching_turns = {
        int(turn)
        for turn, commits in turn_commits.items()
        if isinstance(commits, list) and target_commits & set(str(c) for c in commits)
    }
    if not matching_turns:
        return source

    narrowed = Session(
        session_id=source.session_id,
        harness=source.harness,
        config=source.config,
        prompts=[turn for turn in source.prompts if turn.turn in matching_turns],
        system_context=dict(source.system_context),
        changed_files=list(target.changed_files),
        commits=list(target.commits),
        timestamps=source.timestamps,
    )
    narrowed.system_context["transcript_filtered_to_commits"] = sorted(target_commits)
    narrowed.system_context["transcript_filtered_turns"] = sorted(matching_turns)
    return narrowed


def _bench_record(session: Session) -> dict:
    is_bad = _is_bad_case(session)
    score = 0.0 if is_bad else 1.0
    status = "fail" if is_bad else "pass"
    category = f"survey:{_bad_case_type(session)}" if is_bad else "survey:clean"
    tag = session.tag
    notes = tag.notes if tag and tag.notes else ""
    l0_l1_pass = True
    if session.verification:
        l0_l1_pass = session.verification.l0_pass and session.verification.l1_pass

    return {
        "testcase_id": session.session_id,
        "harness": session.harness,
        "category": category,
        "l0_l1_pass": l0_l1_pass,
        "score": score,
        "verifier_result": {
            "score": score,
            "status": status,
            "category": category,
            "error": notes if is_bad else "",
            "checks": _bench_checks(session, is_bad),
        },
        "diff": "",
        "artifacts_path": None,
        "ai_agent_context": _ai_agent_context(session),
        "survey_session": {
            "session_id": session.session_id,
            "harness": session.harness,
            "config": session.config,
            "bad_case_type": _bad_case_type(session) if is_bad else None,
            "auto_detected": bool(tag and tag.auto_detected),
            "confidence": tag.confidence if tag else None,
            "notes": notes,
            "prompts": [turn.to_dict() for turn in session.prompts],
            "system_context": session.system_context,
            "changed_files": session.changed_files,
            "commits": session.commits,
            "timestamps": session.timestamps,
            "verification": session.verification.to_dict() if session.verification else None,
            "outcome": session.outcome.to_dict() if session.outcome else None,
        },
    }


def _ai_agent_context(session: Session) -> dict:
    ctx = session.system_context
    return {
        "harness": session.harness,
        "transcript_session_id": ctx.get("transcript_session_id"),
        "transcript_match_confidence": ctx.get("transcript_match_confidence"),
        "transcript_path": ctx.get("transcript_path"),
        "codex_session_id": ctx.get("codex_session_id"),
        "total_tokens": ctx.get("total_tokens"),
        "filtered_to_commits": ctx.get("transcript_filtered_to_commits", session.commits),
        "filtered_turns": ctx.get("transcript_filtered_turns"),
        "turns": [
            {
                "turn": turn.turn,
                "agent_input": turn.user_message,
                "agent_output": turn.assistant_summary,
                "tool_calls": turn.tool_calls,
            }
            for turn in session.prompts
        ],
    }


def _bench_checks(session: Session, is_bad: bool) -> list[dict]:
    tag = session.tag
    checks = [
        _check(
            "bad_case_detected",
            not is_bad,
            tag.notes if tag and tag.notes else "",
            "none",
            _bad_case_type(session) if is_bad else "none",
        )
    ]

    if session.verification:
        checks.append(_check(
            "L0",
            session.verification.l0_pass,
            "; ".join(session.verification.l0_details),
            "pass",
            "pass" if session.verification.l0_pass else "fail",
        ))
        checks.append(_check(
            "L1",
            session.verification.l1_pass,
            "; ".join(session.verification.l1_details),
            "pass",
            "pass" if session.verification.l1_pass else "fail",
        ))

    if session.outcome:
        ratio = session.outcome.human_intervention_ratio
        checks.append(_check(
            "human_intervention_ratio",
            ratio <= 0.4,
            "",
            "<= 0.40",
            round(ratio, 4),
        ))
        checks.append(_check(
            "rounds_to_resolution",
            session.outcome.rounds_to_resolution <= 4,
            "",
            "<= 4",
            session.outcome.rounds_to_resolution,
        ))

    return checks


def _check(name: str, passed: bool, detail: str = "", expected=None, actual=None) -> dict:
    return {
        "name": name,
        "passed": passed,
        "detail": detail,
        "expected": expected,
        "actual": actual,
    }


def _is_bad_case(session: Session) -> bool:
    return bool(
        session.tag
        and (session.tag.bad_case_type or session.tag.suggested_type or session.tag.auto_detected)
    )


def _bad_case_type(session: Session) -> str:
    if not session.tag:
        return "unclassified"
    return session.tag.bad_case_type or session.tag.suggested_type or "unclassified"


def _pct(count: int, total: int) -> str:
    if total == 0:
        return "n/a"
    return f"{count / total:.0%}"
