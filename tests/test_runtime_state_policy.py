from datetime import datetime, timedelta, timezone

from agent_bus.models import AgentRuntimeState, PresenceState
from agent_bus.runtime_state import (
    FreshnessThresholds,
    RuntimeFacts,
    derive_presence_state,
    derive_runtime_activity,
    validate_heartbeat_runtime_transition,
)


def iso_age(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def test_rehydrating_times_out_to_suspected_stuck():
    facts = RuntimeFacts(
        runtime_state=AgentRuntimeState.REHYDRATING,
        last_seen_at=iso_age(900),
        active=True,
        ended_at=None,
        has_active_responsibility=True,
    )

    result = derive_runtime_activity(facts, FreshnessThresholds(stale_seconds=300, archive_seconds=3600))

    assert result.runtime_state is AgentRuntimeState.SUSPECTED_STUCK
    assert result.presence_state is PresenceState.STALE
    assert result.conditions["Reachable"].status == "false"
    assert result.conditions["ReplacementRecommended"].status == "true"


def test_rehydrating_times_out_even_without_active_responsibility():
    facts = RuntimeFacts(
        runtime_state=AgentRuntimeState.REHYDRATING,
        last_seen_at=iso_age(900),
        active=True,
        ended_at=None,
        has_active_responsibility=False,
    )

    result = derive_runtime_activity(facts, FreshnessThresholds(stale_seconds=300, archive_seconds=3600))

    assert result.runtime_state is AgentRuntimeState.SUSPECTED_STUCK
    assert result.presence_state is PresenceState.STALE
    assert result.conditions["HasActiveWork"].status == "false"
    assert result.conditions["ReplacementRecommended"].status == "true"


def test_stale_standby_without_responsibility_is_offline_not_main_roster_health():
    facts = RuntimeFacts(
        runtime_state=AgentRuntimeState.STANDBY_READY,
        last_seen_at=iso_age(7200),
        active=True,
        ended_at=None,
        has_active_responsibility=False,
    )

    result = derive_runtime_activity(facts, FreshnessThresholds(stale_seconds=300, archive_seconds=3600))

    assert result.runtime_state is AgentRuntimeState.STANDBY_DEGRADED
    assert result.presence_state is PresenceState.OFFLINE
    assert result.conditions["HasActiveWork"].status == "false"


def test_heartbeat_cannot_unilaterally_set_working_without_binding():
    ok, reason = validate_heartbeat_runtime_transition(
        current=AgentRuntimeState.STANDBY_READY,
        requested=AgentRuntimeState.WORKING,
        has_valid_work_binding=False,
        has_progress_evidence=False,
    )

    assert ok is False
    assert reason == "working_requires_valid_work_binding"
