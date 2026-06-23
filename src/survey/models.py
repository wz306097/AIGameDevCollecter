from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HarnessEvent:
    event_id: str
    harness: str
    session_id: str
    timestamp: str
    event_type: str
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "harness": self.harness,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict) -> HarnessEvent:
        return cls(
            event_id=data["event_id"],
            harness=data["harness"],
            session_id=data["session_id"],
            timestamp=data["timestamp"],
            event_type=data["event_type"],
            payload=data.get("payload", {}),
        )


@dataclass
class Turn:
    turn: int
    user_message: str
    assistant_summary: str
    tool_calls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "turn": self.turn,
            "user_message": self.user_message,
            "assistant_summary": self.assistant_summary,
            "tool_calls": self.tool_calls,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Turn:
        return cls(
            turn=data["turn"],
            user_message=data["user_message"],
            assistant_summary=data["assistant_summary"],
            tool_calls=data.get("tool_calls", []),
        )


@dataclass
class VerificationResult:
    l0_pass: bool = True
    l1_pass: bool = True
    l0_details: list[str] = field(default_factory=list)
    l1_details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "l0_pass": self.l0_pass,
            "l1_pass": self.l1_pass,
            "l0_details": self.l0_details,
            "l1_details": self.l1_details,
        }

    @classmethod
    def from_dict(cls, data: dict) -> VerificationResult:
        return cls(
            l0_pass=data.get("l0_pass", True),
            l1_pass=data.get("l1_pass", True),
            l0_details=data.get("l0_details", []),
            l1_details=data.get("l1_details", []),
        )


@dataclass
class Outcome:
    first_pass_success: bool = False
    rounds_to_resolution: int = 0
    ai_lines_changed: int = 0
    human_lines_changed: int = 0
    token_cost: int = 0
    session_duration_minutes: float = 0.0

    @property
    def human_intervention_ratio(self) -> float:
        total = self.ai_lines_changed + self.human_lines_changed
        if total == 0:
            return 0.0
        return self.human_lines_changed / total

    def to_dict(self) -> dict:
        return {
            "first_pass_success": self.first_pass_success,
            "rounds_to_resolution": self.rounds_to_resolution,
            "ai_lines_changed": self.ai_lines_changed,
            "human_lines_changed": self.human_lines_changed,
            "human_intervention_ratio": self.human_intervention_ratio,
            "token_cost": self.token_cost,
            "session_duration_minutes": self.session_duration_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Outcome:
        return cls(
            first_pass_success=data.get("first_pass_success", False),
            rounds_to_resolution=data.get("rounds_to_resolution", 0),
            ai_lines_changed=data.get("ai_lines_changed", 0),
            human_lines_changed=data.get("human_lines_changed", 0),
            token_cost=data.get("token_cost", 0),
            session_duration_minutes=data.get("session_duration_minutes", 0.0),
        )


@dataclass
class TagInfo:
    bad_case_type: str | None = None
    auto_detected: bool = False
    suggested_type: str | None = None
    confidence: str = "high"
    root_cause: str | None = None
    harness_actionable: bool | None = None
    actionable_suggestion: str | None = None
    intent_match: int | None = None
    would_ship_as_is: bool | None = None
    notes: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in {
            "bad_case_type": self.bad_case_type,
            "auto_detected": self.auto_detected,
            "suggested_type": self.suggested_type,
            "confidence": self.confidence,
            "root_cause": self.root_cause,
            "harness_actionable": self.harness_actionable,
            "actionable_suggestion": self.actionable_suggestion,
            "intent_match": self.intent_match,
            "would_ship_as_is": self.would_ship_as_is,
            "notes": self.notes,
        }.items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> TagInfo:
        return cls(
            bad_case_type=data.get("bad_case_type"),
            auto_detected=data.get("auto_detected", False),
            suggested_type=data.get("suggested_type"),
            confidence=data.get("confidence", "high"),
            root_cause=data.get("root_cause"),
            harness_actionable=data.get("harness_actionable"),
            actionable_suggestion=data.get("actionable_suggestion"),
            intent_match=data.get("intent_match"),
            would_ship_as_is=data.get("would_ship_as_is"),
            notes=data.get("notes"),
        )


@dataclass
class Session:
    session_id: str
    harness: str
    config: dict = field(default_factory=dict)
    prompts: list[Turn] = field(default_factory=list)
    system_context: dict = field(default_factory=dict)
    changed_files: list[str] = field(default_factory=list)
    commits: list[str] = field(default_factory=list)
    verification: VerificationResult | None = None
    outcome: Outcome | None = None
    tag: TagInfo | None = None
    multi_task: bool = False
    task_group: str | None = None
    timestamps: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        result = {
            "session_id": self.session_id,
            "harness": self.harness,
            "config": self.config,
            "prompts": [t.to_dict() for t in self.prompts],
            "system_context": self.system_context,
            "changed_files": self.changed_files,
            "commits": self.commits,
            "timestamps": self.timestamps,
            "multi_task": self.multi_task,
        }
        if self.verification:
            result["verification"] = self.verification.to_dict()
        if self.outcome:
            result["outcome"] = self.outcome.to_dict()
        if self.tag:
            result["tag"] = self.tag.to_dict()
        if self.task_group:
            result["task_group"] = self.task_group
        return result

    @classmethod
    def from_dict(cls, data: dict) -> Session:
        return cls(
            session_id=data["session_id"],
            harness=data["harness"],
            config=data.get("config", {}),
            prompts=[Turn.from_dict(t) for t in data.get("prompts", [])],
            system_context=data.get("system_context", {}),
            changed_files=data.get("changed_files", []),
            commits=data.get("commits", []),
            verification=VerificationResult.from_dict(data["verification"]) if data.get("verification") else None,
            outcome=Outcome.from_dict(data["outcome"]) if data.get("outcome") else None,
            tag=TagInfo.from_dict(data["tag"]) if data.get("tag") else None,
            multi_task=data.get("multi_task", False),
            task_group=data.get("task_group"),
            timestamps=data.get("timestamps", {}),
        )
