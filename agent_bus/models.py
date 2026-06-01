from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class EventType(str, Enum):
    BUS_STARTED = "bus.started"
    EVENT_RECORDED = "event.recorded"
    AGENT_REGISTERED = "agent.registered"
    AGENT_SESSION_STARTED = "agent.session_started"
    AGENT_STATUS_CHANGED = "agent.status_changed"
    INBOX_ENQUEUED = "inbox.enqueued"
    INBOX_DELIVERED = "inbox.delivered"
    INBOX_ACKED = "inbox.acked"
    CONTEXT_CREATED = "context.created"
    CONTEXT_INVALIDATED = "context.invalidated"
    CONTEXT_SUPERSEDED = "context.superseded"
    RUN_CREATED = "run.created"
    TASK_CREATED = "task.created"
    TASK_ASSIGNED = "task.assigned"
    TASK_ACKNOWLEDGED = "task.acknowledged"
    TASK_PROGRESS = "task.progress"
    TASK_BLOCKED = "task.blocked"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_SUPERSEDED = "task.superseded"
    TASK_REASSIGNED = "task.reassigned"
    GATE_OPENED = "gate.opened"
    GATE_RESULT = "gate.result"
    GATE_ESCALATED = "gate.escalated"
    REVIEW_FINDING_CREATED = "review.finding_created"
    REVIEW_FINDING_RESOLVED = "review.finding_resolved"
    REVIEW_CHANGES_REQUESTED = "review.changes_requested"
    ARTIFACT_CREATED = "artifact.created"
    COORDINATION_RECORDED = "coordination.recorded"
    USER_INTERRUPT_CREATED = "user.interrupt_created"
    REPLACEMENT_RECOMMENDED = "replacement.recommended"
    REPLACEMENT_APPROVED = "replacement.approved"


class AgentRuntimeState(str, Enum):
    WAITING_ON_BUS = "WAITING_ON_BUS"
    WAIT_RETURNED_NOOP = "WAIT_RETURNED_NOOP"
    DELIVERED_NOT_ACKED = "DELIVERED_NOT_ACKED"
    WORKING = "WORKING"
    SUSPECTED_STUCK = "SUSPECTED_STUCK"
    INPUT_UNAVAILABLE = "INPUT_UNAVAILABLE"
    CONTEXT_LOST = "CONTEXT_LOST"
    NEEDS_REHYDRATION = "NEEDS_REHYDRATION"
    REHYDRATING = "REHYDRATING"
    STANDBY_READY = "STANDBY_READY"
    STANDBY_DEGRADED = "STANDBY_DEGRADED"
    REPLACED = "REPLACED"


class CapabilityEvidenceSource(str, Enum):
    DECLARED = "declared"
    PROBED = "probed"
    OBSERVED = "observed"
    QA_CONFIRMED = "qa_confirmed"
    USER_ASSIGNED = "user_assigned"


class BusEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: new_id("evt"))
    type: EventType | str = EventType.EVENT_RECORDED
    ts: str = Field(default_factory=utc_now_iso)
    actor: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    seq: int | None = None


class BusMessageLink(BaseModel):
    run_id: str | None = None
    task_ids: list[str] = Field(default_factory=list)
    gate_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)


class BusMessageProjection(BaseModel):
    message_id: str
    bus_event_id: str
    thread_id: str | None = None
    space_id: str | None = None
    sender_agent_id: str | None = None
    sender_name: str
    sender_roles: list[str] = Field(default_factory=list)
    recipient_agent_ids: list[str] = Field(default_factory=list)
    message_type: str
    delivery_state: str
    ack_state: str
    reply_state: str
    priority: str = "normal"
    body: str
    links: BusMessageLink = Field(default_factory=BusMessageLink)
    created_at: str
    updated_at: str


class AgentIdentity(BaseModel):
    agent_id: str
    display_name: str | None = None
    role: str | None = None
    capability_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class AgentSession(BaseModel):
    session_id: str = Field(default_factory=lambda: new_id("ses"))
    agent_id: str
    run_id: str | None = None
    active: bool = True
    runtime_state: AgentRuntimeState = AgentRuntimeState.STANDBY_READY
    started_at: str = Field(default_factory=utc_now_iso)
    last_seen_at: str | None = None
    ended_at: str | None = None
    replaced_by_session_id: str | None = None


class AgentHealth(BaseModel):
    agent_id: str
    session_id: str | None = None
    runtime_state: AgentRuntimeState = AgentRuntimeState.STANDBY_READY
    health_score: float = 1.0
    stale: bool = False
    input_available: bool = True
    context_valid: bool = True
    reason: str | None = None
    checked_at: str = Field(default_factory=utc_now_iso)


class AgentCapability(BaseModel):
    capability_id: str = Field(default_factory=lambda: new_id("cap"))
    agent_id: str
    name: str
    confidence: float = 0.0
    evidence_sources: list[CapabilityEvidenceSource] = Field(default_factory=list)
    last_observed_at: str | None = None
    updated_at: str = Field(default_factory=utc_now_iso)


class InboxItem(BaseModel):
    inbox_id: str = Field(default_factory=lambda: new_id("inbox"))
    agent_id: str
    priority: int = 0
    kind: str
    status: str = "queued"
    payload: dict[str, Any] = Field(default_factory=dict)
    context_packet_id: str | None = None
    dedupe_key: str | None = None
    visible_at: str = Field(default_factory=utc_now_iso)
    delivered_at: str | None = None
    acked_at: str | None = None
    expires_at: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class ContextPacket(BaseModel):
    packet_id: str = Field(default_factory=lambda: new_id("ctx"))
    version: int = 1
    agent_id: str
    task_id: str | None = None
    run_id: str | None = None
    status: str = "active"
    summary: str = ""
    instructions: list[str] | dict[str, Any] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    created_from_event_id: str | None = None
    supersedes_packet_id: str | None = None
    superseded_by_packet_id: str | None = None
    invalidated_by_event_id: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    invalidated_at: str | None = None


class RunState(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskState(str, Enum):
    CREATED = "created"
    ASSIGNED = "assigned"
    ACKNOWLEDGED = "acknowledged"
    WORKING = "working"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    REASSIGNED = "reassigned"


class GateState(str, Enum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    EXPIRED = "expired"


class ReviewFindingStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class CoordinationRecord(BaseModel):
    record_id: str = Field(default_factory=lambda: new_id("coord"))
    kind: str
    run_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)
    expires_at: str | None = None


class RunRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: new_id("run"))
    title: str
    objective: str = ""
    status: RunState = RunState.CREATED
    created_by: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class TaskRecord(BaseModel):
    task_id: str = Field(default_factory=lambda: new_id("task"))
    run_id: str | None = None
    title: str
    owner_agent_id: str | None = None
    assignee_agent_id: str | None = None
    status: TaskState = TaskState.CREATED
    priority: int = 0
    parent_task_id: str | None = None
    supersedes_task_id: str | None = None
    blocked_reason: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    completed_at: str | None = None
    failed_at: str | None = None


class GateRecord(BaseModel):
    gate_id: str = Field(default_factory=lambda: new_id("gate"))
    run_id: str | None = None
    task_id: str | None = None
    name: str
    state: GateState = GateState.OPEN
    risk: str = "normal"
    owner_agent_id: str | None = None
    requested_by: str | None = None
    decision_by: str | None = None
    reason: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    resolved_at: str | None = None


class ReviewFinding(BaseModel):
    finding_id: str = Field(default_factory=lambda: new_id("finding"))
    severity: str
    category: str
    file_path: str | None = None
    evidence: str = ""
    requested_change: str = ""
    blocking: bool = False
    resolved_by: str | None = None
    status: ReviewFindingStatus = ReviewFindingStatus.OPEN
    run_id: str | None = None
    task_id: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)
    resolved_at: str | None = None


class ArtifactRecord(BaseModel):
    artifact_id: str = Field(default_factory=lambda: new_id("artifact"))
    run_id: str | None = None
    task_id: str | None = None
    kind: str
    uri: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
