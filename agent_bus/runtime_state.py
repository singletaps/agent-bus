from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .models import AgentRuntimeState, PresenceState, RuntimeCondition, utc_now_iso


@dataclass(frozen=True)
class FreshnessThresholds:
    stale_seconds: float = 300.0
    archive_seconds: float = 3600.0


@dataclass(frozen=True)
class RuntimeFacts:
    runtime_state: AgentRuntimeState
    last_seen_at: str | None
    active: bool
    ended_at: str | None
    has_active_responsibility: bool


@dataclass(frozen=True)
class RuntimeActivityProjection:
    runtime_state: AgentRuntimeState
    presence_state: PresenceState
    stale: bool
    reason: str
    health_score: float
    conditions: dict[str, RuntimeCondition]


ACTIVE_TIMEOUT_STATES = {
    AgentRuntimeState.DELIVERED_NOT_ACKED,
    AgentRuntimeState.WORKING,
    AgentRuntimeState.WAITING_FOR_COMMIT,
    AgentRuntimeState.WAITING_FOR_REVIEW,
    AgentRuntimeState.WAITING_FOR_GATE,
}

RECOVERY_TIMEOUT_STATES = {
    AgentRuntimeState.REHYDRATING,
}

STANDBY_TIMEOUT_STATES = {
    AgentRuntimeState.STANDBY_READY,
    AgentRuntimeState.WAITING_ON_BUS,
    AgentRuntimeState.WAIT_RETURNED_NOOP,
}


def derive_presence_state(last_seen_at: str | None, thresholds: FreshnessThresholds) -> PresenceState:
    age = age_seconds(last_seen_at)
    if age is None:
        return PresenceState.UNKNOWN
    if age <= thresholds.stale_seconds:
        return PresenceState.ONLINE
    if age <= thresholds.archive_seconds:
        return PresenceState.STALE
    return PresenceState.OFFLINE


def derive_runtime_activity(facts: RuntimeFacts, thresholds: FreshnessThresholds) -> RuntimeActivityProjection:
    presence = (
        PresenceState.OFFLINE
        if not facts.active or facts.ended_at
        else derive_presence_state(facts.last_seen_at, thresholds)
    )
    state = facts.runtime_state
    stale = presence in {PresenceState.STALE, PresenceState.OFFLINE}
    reason = "fresh"

    if stale and state in RECOVERY_TIMEOUT_STATES:
        state = AgentRuntimeState.SUSPECTED_STUCK
        reason = "rehydrate_timeout"
    elif stale and facts.has_active_responsibility and state in ACTIVE_TIMEOUT_STATES:
        state = AgentRuntimeState.SUSPECTED_STUCK
        reason = "active_responsibility_missing_heartbeat"
    elif stale and not facts.has_active_responsibility and state in STANDBY_TIMEOUT_STATES:
        state = AgentRuntimeState.STANDBY_DEGRADED
        reason = "standby_missing_heartbeat"
    elif stale:
        reason = "missing_heartbeat"

    return RuntimeActivityProjection(
        runtime_state=state,
        presence_state=presence,
        stale=stale,
        reason=reason,
        health_score=_health_score(state, presence),
        conditions=_conditions(
            presence_state=presence,
            runtime_state=state,
            has_active_responsibility=facts.has_active_responsibility,
            reason=reason,
        ),
    )


def validate_heartbeat_runtime_transition(
    *,
    current: AgentRuntimeState,
    requested: AgentRuntimeState | None,
    has_valid_work_binding: bool,
    has_progress_evidence: bool,
) -> tuple[bool, str]:
    if requested is None or requested is current:
        return True, "heartbeat_refresh"
    if requested is AgentRuntimeState.WORKING and not (has_valid_work_binding or has_progress_evidence):
        return False, "working_requires_valid_work_binding"
    return True, "heartbeat_state_refresh"


def age_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def _condition(
    type: str,
    status: str,
    reason: str,
    severity: str,
    message: str | None = None,
) -> RuntimeCondition:
    return RuntimeCondition(
        type=type,
        status=status,
        reason=reason,
        message=message,
        severity=severity,
        source="runtime_state_policy",
        last_transition_at=utc_now_iso(),
    )


def _conditions(
    *,
    presence_state: PresenceState,
    runtime_state: AgentRuntimeState,
    has_active_responsibility: bool,
    reason: str,
) -> dict[str, RuntimeCondition]:
    reachable = presence_state is PresenceState.ONLINE
    replacement_recommended = runtime_state is AgentRuntimeState.SUSPECTED_STUCK
    return {
        "Ready": _condition(
            "Ready",
            "false" if replacement_recommended else "true",
            reason,
            "warning" if replacement_recommended else "info",
        ),
        "Reachable": _condition(
            "Reachable",
            "true" if reachable else "false",
            reason,
            "info" if reachable else "warning",
        ),
        "HasActiveWork": _condition(
            "HasActiveWork",
            "true" if has_active_responsibility else "false",
            "active_responsibility_present" if has_active_responsibility else "no_active_responsibility",
            "info",
        ),
        "ReplacementRecommended": _condition(
            "ReplacementRecommended",
            "true" if replacement_recommended else "false",
            reason if replacement_recommended else "replacement_not_indicated",
            "warning" if replacement_recommended else "info",
        ),
    }


def _health_score(runtime_state: AgentRuntimeState, presence_state: PresenceState) -> float:
    if runtime_state is AgentRuntimeState.SUSPECTED_STUCK:
        return 0.2
    if runtime_state in {AgentRuntimeState.CONTEXT_LOST, AgentRuntimeState.NEEDS_REHYDRATION}:
        return 0.3
    if presence_state is PresenceState.OFFLINE:
        return 0.4
    if presence_state is PresenceState.STALE:
        return 0.6
    if presence_state is PresenceState.UNKNOWN:
        return 0.5
    return 1.0
