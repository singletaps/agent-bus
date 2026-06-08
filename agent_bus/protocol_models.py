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


class ProjectionEffect(str, Enum):
    COMMIT = "COMMIT"
    AUDIT_ONLY = "AUDIT_ONLY"
    REJECT = "REJECT"


class FencingResult(str, Enum):
    VALID = "VALID"
    MISSING = "MISSING"
    INVALID = "INVALID"
    STALE_EPOCH = "STALE_EPOCH"
    WRONG_SESSION = "WRONG_SESSION"
    NOT_REQUIRED = "NOT_REQUIRED"


class SessionRole(str, Enum):
    PRIMARY = "primary"
    STANDBY = "standby"
    REPLACED = "replaced"
    QUARANTINED = "quarantined"
    RETIRED = "retired"


class PacketKind(str, Enum):
    ASSIGNMENT = "assignment"
    HANDOFF = "handoff"
    REHYDRATION = "rehydration"
    REVIEW = "review"
    REPLAN = "replan"
    GATE_RESOLUTION = "gate_resolution"
    USER_INTERRUPT = "user_interrupt"


class TaskClaimKind(str, Enum):
    ACK = "ack"
    PROGRESS = "progress"
    BLOCKER = "blocker"
    COMPLETION = "completion"
    FAILURE = "failure"
    ARTIFACT = "artifact"
    HANDOFF = "handoff"


class PrincipalType(str, Enum):
    USER = "user"
    CONTROLLER = "controller"
    AGENT = "agent"
    SYSTEM = "system"


class ClaimStatus(str, Enum):
    PENDING = "pending"
    NEEDS_FENCING = "needs_fencing"
    COMMITTED = "committed"
    REJECTED = "rejected"


class BindingStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"
    ENDED = "ended"


class Principal(BaseModel):
    principal_id: str = Field(default_factory=lambda: new_id("principal"))
    principal_type: PrincipalType
    agent_id: str | None = None
    session_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class SessionFenceRegistration(BaseModel):
    session_id: str
    agent_id: str | None = None
    session_epoch: int
    raw_token: str
    token_hash: str
    session_role: SessionRole = SessionRole.PRIMARY


class FencingCheck(BaseModel):
    allowed: bool
    result: FencingResult
    reason: str | None = None
    session_id: str | None = None
    session_epoch: int | None = None
    agent_id: str | None = None


class AuthorityDecision(BaseModel):
    allowed: bool
    reason: str | None = None
    action: str
    actor: str | None = None
    actor_role: str | None = None
    principal_id: str | None = None


class PolicyDecision(BaseModel):
    allowed: bool
    reason: str | None = None
    checks: list[str] = Field(default_factory=list)


class ProtocolViolation(BaseModel):
    violation_id: str = Field(default_factory=lambda: new_id("vio"))
    attempted_event_id: str | None = None
    actor: str | None = None
    actor_role: str | None = None
    action: str
    reason: str
    fencing_result: FencingResult | str | None = None
    projection_effect: ProjectionEffect | str = ProjectionEffect.REJECT
    run_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    context_packet_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now_iso)


class ProjectionEffectRecord(BaseModel):
    effect_id: str = Field(default_factory=lambda: new_id("effect"))
    event_id: str | None = None
    attempted_event_id: str | None = None
    effect: ProjectionEffect
    reason: str | None = None
    target_table: str | None = None
    target_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class TaskClaimRecord(BaseModel):
    claim_id: str = Field(default_factory=lambda: new_id("claim"))
    claim_kind: TaskClaimKind | str
    task_id: str
    run_id: str | None = None
    agent_id: str | None = None
    session_id: str | None = None
    session_epoch: int | None = None
    context_packet_id: str | None = None
    status: ClaimStatus | str = ClaimStatus.PENDING
    payload: dict[str, Any] = Field(default_factory=dict)
    created_from_event_id: str | None = None
    committed_by_event_id: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class ProtocolWriteResult(BaseModel):
    accepted: bool
    event_id: str | None = None
    seq: int | None = None
    violation_id: str | None = None
    effect_id: str | None = None
    projection_effect: ProjectionEffect
    fencing_result: FencingResult
    reason: str | None = None
    claim_id: str | None = None
    claim_status: ClaimStatus | str | None = None
