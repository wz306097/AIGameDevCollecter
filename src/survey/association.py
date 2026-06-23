from __future__ import annotations

from survey.models import HarnessEvent


def associate_commit(
    changed_files: set[str],
    events: list[HarnessEvent],
) -> tuple[str | None, float, str]:
    session_files: dict[str, set[str]] = {}
    for event in events:
        if event.event_type == "file_write":
            fp = event.payload.get("file_path", "")
            if fp:
                session_files.setdefault(event.session_id, set()).add(fp)

    best_session = None
    best_ratio = 0.0

    for session_id, files in session_files.items():
        overlap = len(files & changed_files)
        if not overlap:
            continue
        ratio = overlap / len(changed_files)
        if ratio > best_ratio:
            best_ratio = ratio
            best_session = session_id

    if best_ratio > 0.5:
        return best_session, best_ratio, "high"
    elif best_ratio >= 0.2:
        return best_session, best_ratio, "low"
    else:
        return None, best_ratio, "none"
