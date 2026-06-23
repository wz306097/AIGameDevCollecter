from survey.badcase import detect_bad_case, suggest_classification
from survey.models import Session, Turn, Outcome, VerificationResult, TagInfo


def test_l0_fail_is_bad_case():
    session = Session(
        session_id="s1",
        harness="cc",
        verification=VerificationResult(l0_pass=False, l0_details=["crash"]),
        outcome=Outcome(first_pass_success=False, rounds_to_resolution=1),
    )
    tag = detect_bad_case(session)
    assert tag is not None
    assert tag.auto_detected is True


def test_l1_fail_is_bad_case():
    session = Session(
        session_id="s2",
        harness="cc",
        verification=VerificationResult(l0_pass=True, l1_pass=False, l1_details=["signal missing"]),
        outcome=Outcome(first_pass_success=False, rounds_to_resolution=1),
    )
    tag = detect_bad_case(session)
    assert tag is not None


def test_high_human_intervention_is_bad_case():
    session = Session(
        session_id="s3",
        harness="cc",
        verification=VerificationResult(l0_pass=True, l1_pass=True),
        outcome=Outcome(first_pass_success=False, rounds_to_resolution=2, ai_lines_changed=30, human_lines_changed=25),
    )
    tag = detect_bad_case(session)
    assert tag is not None
    assert tag.confidence != "none"


def test_many_rounds_is_bad_case():
    session = Session(
        session_id="s4",
        harness="cc",
        verification=VerificationResult(l0_pass=True, l1_pass=True),
        outcome=Outcome(first_pass_success=False, rounds_to_resolution=5),
    )
    tag = detect_bad_case(session)
    assert tag is not None


def test_clean_session_not_bad_case():
    session = Session(
        session_id="s5",
        harness="cc",
        verification=VerificationResult(l0_pass=True, l1_pass=True),
        outcome=Outcome(first_pass_success=True, rounds_to_resolution=1, ai_lines_changed=20, human_lines_changed=0),
    )
    tag = detect_bad_case(session)
    assert tag is None


def test_suggest_a2_for_signal_fail():
    session = Session(
        session_id="s6",
        harness="cc",
        verification=VerificationResult(l0_pass=True, l1_pass=False, l1_details=["signal 'timeout' target missing"]),
        outcome=Outcome(),
    )
    suggestion = suggest_classification(session)
    assert suggestion == "A2"


def test_suggest_b_for_correction_prompt():
    session = Session(
        session_id="s7",
        harness="cc",
        prompts=[
            Turn(turn=1, user_message="实现横版跳跃", assistant_summary="...", tool_calls=[]),
            Turn(turn=2, user_message="不对，我要的是俯视角移动", assistant_summary="...", tool_calls=[]),
        ],
        verification=VerificationResult(l0_pass=True, l1_pass=True),
        outcome=Outcome(first_pass_success=False, rounds_to_resolution=2),
    )
    suggestion = suggest_classification(session)
    assert suggestion is not None
    assert suggestion.startswith("B")


def test_suggest_c_for_high_intervention_but_l2_pass():
    session = Session(
        session_id="s8",
        harness="cc",
        verification=VerificationResult(l0_pass=True, l1_pass=True),
        outcome=Outcome(first_pass_success=False, rounds_to_resolution=2, ai_lines_changed=30, human_lines_changed=25),
    )
    suggestion = suggest_classification(session)
    assert suggestion is not None
    assert suggestion.startswith("C")
