from __future__ import annotations

import re

from survey.models import Session, TagInfo

CORRECTION_PATTERNS_ZH = re.compile(r"不是|不对|我要的是|错了|不要|搞反了|重新")
CORRECTION_PATTERNS_EN = re.compile(r"no[,.]|wrong|not what|I meant|I wanted|that's not|redo", re.IGNORECASE)


def detect_bad_case(session: Session) -> TagInfo | None:
    if not session.verification and not session.outcome:
        return None

    reasons: list[str] = []

    if session.verification:
        if not session.verification.l0_pass:
            reasons.append("L0 fail")
        if not session.verification.l1_pass:
            reasons.append("L1 fail")

    if session.outcome:
        if session.outcome.human_intervention_ratio > 0.4:
            reasons.append(f"human_intervention_ratio={session.outcome.human_intervention_ratio:.2f}")
        if session.outcome.rounds_to_resolution > 4:
            reasons.append(f"rounds_to_resolution={session.outcome.rounds_to_resolution}")

    if not reasons:
        return None

    suggested = suggest_classification(session)

    return TagInfo(
        auto_detected=True,
        suggested_type=suggested,
        confidence="high" if any(r.startswith("L") for r in reasons) else "low",
        notes="; ".join(reasons),
    )


def suggest_classification(session: Session) -> str | None:
    if session.verification:
        if not session.verification.l1_pass:
            signal_issues = [d for d in session.verification.l1_details if "signal" in d.lower()]
            if signal_issues:
                return "A2"
            return "A1"

        if not session.verification.l0_pass:
            return "A1"

    has_correction = False
    for turn in session.prompts:
        if CORRECTION_PATTERNS_ZH.search(turn.user_message) or CORRECTION_PATTERNS_EN.search(turn.user_message):
            has_correction = True
            break

    if has_correction:
        return "B1"

    if session.outcome and session.outcome.human_intervention_ratio > 0.4:
        return "C1"

    return None
