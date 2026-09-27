"""Shared KIFACH data shapes.

These Pydantic models are the contract between media processing, the vision
providers, the deterministic engine, the HTTP API, and the frontend. Frontend
types are generated from the JSON Schema of these models, so field names here
are the field names the UI reads.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


def utc_now() -> datetime:
    """Timezone-aware creation timestamp. Never called inside the pure engine."""
    return datetime.now(timezone.utc)


class Provenance(str, Enum):
    """Where an observation or description actually came from."""

    LIVE = "LIVE"  # a real model call made during this run
    CACHED = "CACHED"  # a genuine model response replayed from disk cache
    MOCK = "MOCK"  # a scripted offline response, never a model result


# ---------------------------------------------------------------------------
# Media and evidence
# ---------------------------------------------------------------------------


class Frame(BaseModel):
    """A sampled frame kept with its true source timestamp."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(ge=0, description="Sample index within the video")
    timestamp_s: float = Field(ge=0, description="Source video timestamp in seconds")
    media_path: str = Field(description="Path relative to the media root")
    sha256: str = Field(min_length=64, max_length=64)


class EvidenceRef(BaseModel):
    """A pointer a human can click to inspect what the system saw."""

    video_id: str
    t_start: float = Field(ge=0)
    t_end: float = Field(ge=0)
    frame_path: str | None = None
    note: str | None = None

    @field_validator("t_end")
    @classmethod
    def _end_after_start(cls, value: float, info: ValidationInfo) -> float:
        start = info.data.get("t_start")
        if start is not None and value < start:
            raise ValueError("t_end must not precede t_start")
        return value


class VideoMeta(BaseModel):
    """A stored upload plus what frame extraction found in it."""

    video_id: str
    filename: str
    content_type: str
    size_bytes: int
    duration_s: float
    fps_source: float
    width: int
    height: int
    sha256: str
    path: str
    frames: list[Frame] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    sample_fps: float = 2.0
    scenario_hint: str | None = Field(
        default=None,
        description=(
            "Scenario id recorded for a bundled sample video, used only to key "
            "the offline mock provider."
        ),
    )


class Window(BaseModel):
    """A contiguous group of frames analysed as one unit."""

    window_id: str
    t_start: float = Field(ge=0)
    t_end: float = Field(ge=0)
    frame_indexes: list[int] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Expert-side window description
# ---------------------------------------------------------------------------


class WindowDescription(BaseModel):
    """What a provider reports seeing in one expert window.

    Nothing here is a judgement about correctness. The limitations field is
    where a provider says what it could not see.
    """

    window_id: str
    t_start: float
    t_end: float
    objects: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    candidate_steps: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence: EvidenceRef
    provenance: Provenance = Provenance.MOCK


# ---------------------------------------------------------------------------
# Skill graph
# ---------------------------------------------------------------------------


class RuleKind(str, Enum):
    ORDER = "order"
    SAFETY = "safety"


class OrderingRule(BaseModel):
    """The before step must happen before the after step, with a stated reason."""

    rule_id: str
    kind: RuleKind = RuleKind.ORDER
    before: str
    after: str
    reason: str
    proposed_by_model: bool = True
    confirmed_by_expert: bool = False


class Step(BaseModel):
    step_id: str
    title: str = Field(min_length=1)
    action: str = ""
    objects: list[str] = Field(default_factory=list)
    description: str = ""
    checkpoint: str = Field(
        default="", description="What must be visible for this step to count as done"
    )
    common_mistakes: list[str] = Field(default_factory=list)
    required: bool = True
    depends_on: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    proposed_by_model: bool = True


class SkillStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class ReviewInfo(BaseModel):
    """Who approved what. Publication requires expert review."""

    reviewed: bool = False
    reviewed_at: datetime | None = None
    edited_steps: list[str] = Field(default_factory=list)
    confirmed_rules: list[str] = Field(default_factory=list)
    reviewer_note: str = ""


class SkillGraph(BaseModel):
    skill_id: str
    title: str = Field(min_length=1)
    summary: str = ""
    source_video_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    status: SkillStatus = SkillStatus.DRAFT
    objects: list[str] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    rules: list[OrderingRule] = Field(default_factory=list)
    review: ReviewInfo = Field(default_factory=ReviewInfo)
    provenance: Provenance = Provenance.MOCK
    validation_flags: list[str] = Field(
        default_factory=list,
        description="Problems found in model output that a human must resolve.",
    )


class GraphProposal(BaseModel):
    """A raw model proposal, before ids are reconciled and validation runs."""

    title: str = Field(min_length=1)
    summary: str = ""
    objects: list[str] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    rules: list[OrderingRule] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    code: str
    message: str
    step_id: str | None = None
    rule_id: str | None = None


class ValidationResult(BaseModel):
    ok: bool
    issues: list[ValidationIssue] = Field(default_factory=list)

    def message(self) -> str:
        return "; ".join(issue.message for issue in self.issues)


# ---------------------------------------------------------------------------
# Learner observation
# ---------------------------------------------------------------------------


class ObservationStatus(str, Enum):
    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    UNDONE = "undone"
    ABSENT = "absent"  # checkpoint area visible, expected result not there
    UNCERTAIN = "uncertain"  # could not tell


class Observation(BaseModel):
    observation_id: str
    window_id: str
    step_id: str
    status: ObservationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    t_start: float = Field(ge=0)
    t_end: float = Field(ge=0)
    evidence: EvidenceRef
    rationale: str = ""
    provenance: Provenance = Provenance.MOCK


class ObservationSet(BaseModel):
    video_id: str | None = None
    skill_id: str | None = None
    observations: list[Observation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    provenance: Provenance = Provenance.MOCK


# ---------------------------------------------------------------------------
# Engine output
# ---------------------------------------------------------------------------


class StepState(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    SKIPPED = "skipped"  # only with explicit absence evidence
    VIOLATION = "violation"
    UNCERTAIN = "uncertain"


class EngineEventType(str, Enum):
    STEP_STARTED = "step_started"
    STEP_DONE = "step_done"
    STEP_REVERTED = "step_reverted"
    STEP_SKIPPED = "step_skipped"
    ORDER_VIOLATION = "order_violation"
    PREREQ_UNCONFIRMED = "prereq_unconfirmed"
    LOW_CONFIDENCE_IGNORED = "low_confidence_ignored"
    UNCERTAIN_OBSERVATION = "uncertain_observation"
    ABSENCE_RECORDED = "absence_recorded"
    DUPLICATE_IGNORED = "duplicate_ignored"
    CONFIRMATION_PENDING = "confirmation_pending"
    ALERT_RESOLVED = "alert_resolved"
    MISSING_REQUIRED = "missing_required"
    VERDICT = "verdict"


class EngineEvent(BaseModel):
    seq: int
    type: EngineEventType
    step_id: str | None = None
    rule_id: str | None = None
    alert_id: str | None = None
    t: float = Field(ge=0, description="Source time of the triggering observation")
    message: str
    observation_id: str | None = None
    evidence: EvidenceRef | None = None


class AlertKind(str, Enum):
    WRONG_ORDER = "wrong_order"
    MISSING_REQUIRED = "missing_required"
    PREREQ_UNCONFIRMED = "prereq_unconfirmed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Alert(BaseModel):
    alert_id: str
    kind: AlertKind
    step_id: str | None = None
    rule_id: str | None = None
    message: str
    opened_at: float
    opened_evidence: EvidenceRef | None = None
    resolved: bool = False
    resolved_at: float | None = None
    resolved_evidence: EvidenceRef | None = None
    supported: bool = Field(
        default=True,
        description=(
            "False when the alert rests on missing rather than absence evidence, "
            "which cannot support a failure verdict."
        ),
    )


class Verdict(str, Enum):
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    INCONCLUSIVE = "INCONCLUSIVE"


class EngineConfig(BaseModel):
    """Explicit engine configuration. Part of the replay key."""

    model_config = ConfigDict(frozen=True)

    min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    confirmations_required: int = Field(default=1, ge=1)
    live_confirmations_required: int = Field(default=2, ge=1)
    independent_gap_s: float = Field(
        default=1.0,
        ge=0.0,
        description=(
            "Two observations of one step count as independent confirmations only "
            "if their source windows start at least this far apart, so overlapping "
            "windows cannot confirm the same event twice."
        ),
    )
    mode: Literal["upload", "live"] = "upload"

    def required_confirmations(self) -> int:
        if self.mode == "live":
            return self.live_confirmations_required
        return self.confirmations_required


class EngineResult(BaseModel):
    step_states: dict[str, StepState] = Field(default_factory=dict)
    events: list[EngineEvent] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)
    verdict: Verdict = Verdict.INCONCLUSIVE
    reasons: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Attempt
# ---------------------------------------------------------------------------


class AttemptStatus(str, Enum):
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class Attempt(BaseModel):
    attempt_id: str
    skill_id: str
    media_id: str | None = None
    live_session_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    status: AttemptStatus = AttemptStatus.RUNNING
    mode: Literal["upload", "live"] = "upload"
    config: EngineConfig = Field(default_factory=EngineConfig)
    observations: list[Observation] = Field(default_factory=list)
    events: list[EngineEvent] = Field(default_factory=list)
    step_states: dict[str, StepState] = Field(default_factory=dict)
    alerts: list[Alert] = Field(default_factory=list)
    verdict: Verdict = Verdict.INCONCLUSIVE
    reasons: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    provenance: Provenance = Provenance.MOCK
    error: str | None = None


class SkillSummary(BaseModel):
    """Library card payload."""

    skill_id: str
    title: str
    summary: str
    status: SkillStatus
    step_count: int
    rule_count: int
    created_at: datetime
    source_video_id: str | None = None
    provenance: Provenance = Provenance.MOCK
    reviewed: bool = False
    last_attempt_id: str | None = None
    last_verdict: Verdict | None = None


class ProviderHealth(BaseModel):
    provider: str
    model: str | None = None
    configured: bool
    cache_mode: str
    provenance_label: Provenance
    detail: str = ""


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    provider: ProviderHealth
    media_root: str
    frontend_built: bool


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
