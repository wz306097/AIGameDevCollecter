from __future__ import annotations

from collections import defaultdict

from survey.models import Session


def generate_report(sessions: list[Session], period_label: str) -> str:
    lines: list[str] = []
    lines.append(f"## Survey Report ({period_label})")
    lines.append("")

    bad_cases = [s for s in sessions if s.tag and s.tag.bad_case_type]

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
            type_counts[s.tag.bad_case_type] += 1

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
            notes = s.tag.notes or ""
            lines.append(f"{i}. **[{s.tag.bad_case_type}] {s.session_id}** — {s.harness}")
            if intent:
                lines.append(f"   Task: \"{intent}\"")
            if notes:
                lines.append(f"   Notes: {notes}")
            lines.append("")

    return "\n".join(lines)


def _pct(count: int, total: int) -> str:
    if total == 0:
        return "—"
    return f"{count / total:.0%}"
