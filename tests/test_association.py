from survey.association import associate_commit
from survey.models import HarnessEvent


def _make_events(session_id: str, files: list[str]) -> list[HarnessEvent]:
    return [
        HarnessEvent(
            event_id=f"evt_{i}",
            harness="claude-code",
            session_id=session_id,
            timestamp="2026-06-18T10:00:00Z",
            event_type="file_write",
            payload={"file_path": f},
        )
        for i, f in enumerate(files)
    ]


def test_high_overlap_associates():
    events = _make_events("s1", ["a.gd", "b.gd", "c.gd"])
    sid, ratio, conf = associate_commit({"a.gd", "b.gd", "c.gd"}, events)
    assert sid == "s1"
    assert ratio == 1.0
    assert conf == "high"


def test_partial_overlap_low_confidence():
    events = _make_events("s1", ["a.gd", "b.gd"])
    sid, ratio, conf = associate_commit({"a.gd", "b.gd", "c.gd", "d.gd"}, events)
    assert sid == "s1"
    assert ratio == 0.5
    assert conf == "low"


def test_no_overlap_returns_none():
    events = _make_events("s1", ["x.gd", "y.gd"])
    sid, ratio, conf = associate_commit({"a.gd", "b.gd"}, events)
    assert sid is None
    assert conf == "none"


def test_picks_best_session():
    events = (
        _make_events("s1", ["a.gd"])
        + _make_events("s2", ["a.gd", "b.gd", "c.gd"])
    )
    sid, ratio, conf = associate_commit({"a.gd", "b.gd", "c.gd"}, events)
    assert sid == "s2"
    assert conf == "high"
