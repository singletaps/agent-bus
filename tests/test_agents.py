from __future__ import annotations

import pytest

from agent_bus.agents import AgentDirectory, AgentDirectoryError
from agent_bus.models import AgentRuntimeState, CapabilityEvidenceSource


def test_migrate_persists_identity_session_health_and_capabilities_across_reload(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    identity = directory.register_identity(
        "worker.backend",
        display_name="Backend",
        role="worker",
        declared_capabilities=["python"],
    )
    first = directory.start_session("worker.backend", session_id="session-1")
    second = directory.start_session("worker.backend", session_id="session-2")
    directory.report_context_loss(second.session_id, reason="context window reset")
    directory.record_capability_evidence(
        "worker.backend",
        "python",
        CapabilityEvidenceSource.QA_CONFIRMED,
        observed_at="2026-05-28T03:00:00Z",
    )
    directory.close()

    reloaded = AgentDirectory(db_path=db_path)

    assert reloaded.get_identity("worker.backend").agent_id == identity.agent_id
    assert reloaded.get_identity("worker.backend").role == "worker"
    assert [session.session_id for session in reloaded.list_sessions("worker.backend")] == [
        first.session_id,
        second.session_id,
    ]
    assert reloaded.get_active_session("worker.backend").session_id == second.session_id
    assert reloaded.get_health(second.session_id).runtime_state is AgentRuntimeState.CONTEXT_LOST
    assert reloaded.get_health(second.session_id).context_valid is False
    assert reloaded.get_health(second.session_id).reason == "context window reset"
    capabilities = reloaded.list_capabilities("worker.backend")
    assert len(capabilities) == 1
    assert capabilities[0].name == "python"
    assert capabilities[0].confidence == pytest.approx(0.9025)
    assert capabilities[0].last_observed_at == "2026-05-28T03:00:00Z"
    assert capabilities[0].evidence_sources == [
        CapabilityEvidenceSource.DECLARED,
        CapabilityEvidenceSource.QA_CONFIRMED,
    ]


def test_durable_replacement_survives_directory_reconstruction(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("worker.docs")
    old = directory.start_session("worker.docs", session_id="old")
    replacement = directory.start_session("worker.docs", session_id="replacement", activate=False)

    directory.replace_session(old.session_id, replacement.session_id)
    directory.close()

    reloaded = AgentDirectory(db_path=db_path)

    assert reloaded.get_session("old").runtime_state is AgentRuntimeState.REPLACED
    assert reloaded.get_session("old").replaced_by_session_id == "replacement"
    assert reloaded.get_health("old").health_score == 0.0
    assert reloaded.get_active_session("worker.docs").session_id == "replacement"


def test_same_identity_can_create_multiple_sessions_and_switch_active_session():
    directory = AgentDirectory()
    identity = directory.register_identity("worker.backend", display_name="Backend", role="worker")

    first = directory.start_session("worker.backend", session_id="session-1")
    second = directory.start_session("worker.backend", session_id="session-2")

    assert identity.agent_id == "worker.backend"
    assert [session.session_id for session in directory.list_sessions("worker.backend")] == [
        "session-1",
        "session-2",
    ]
    assert directory.get_active_session("worker.backend").session_id == "session-2"
    assert directory.get_session("session-1").active is False
    assert directory.get_session("session-2").active is True

    reactivated = directory.switch_active_session("worker.backend", "session-1")

    assert reactivated.session_id == "session-1"
    assert directory.get_active_session("worker.backend").session_id == "session-1"
    assert directory.get_session("session-1").active is True
    assert directory.get_session("session-2").active is False
    assert directory.get_identity("worker.backend") is identity


def test_context_loss_degrades_session_health_without_erasing_capability_history():
    directory = AgentDirectory()
    directory.register_identity("worker.frontend", declared_capabilities=["react"])
    session = directory.start_session("worker.frontend", session_id="session-1")
    declared_capability = directory.list_capabilities("worker.frontend")[0]

    health = directory.report_context_loss(session.session_id, reason="compression failed")

    assert health.runtime_state is AgentRuntimeState.CONTEXT_LOST
    assert health.health_score < 1.0
    assert health.stale is True
    assert health.context_valid is False
    assert health.reason == "compression failed"
    assert directory.get_identity("worker.frontend").agent_id == "worker.frontend"
    assert directory.get_active_session("worker.frontend").session_id == session.session_id
    assert directory.list_capabilities("worker.frontend")[0].capability_id == declared_capability.capability_id
    assert directory.list_capabilities("worker.frontend")[0].evidence_sources == [
        CapabilityEvidenceSource.DECLARED
    ]


def test_capability_confidence_and_freshness_update_from_evidence_sources():
    directory = AgentDirectory()
    directory.register_identity("qa")

    declared = directory.record_capability_evidence(
        "qa",
        "pytest",
        "declared",
        observed_at="2026-05-28T01:00:00Z",
    )
    qa_confirmed = directory.record_capability_evidence(
        "qa",
        "pytest",
        CapabilityEvidenceSource.QA_CONFIRMED,
        observed_at="2026-05-28T02:00:00Z",
    )

    assert qa_confirmed.capability_id == declared.capability_id
    assert qa_confirmed.confidence == pytest.approx(0.9025)
    assert qa_confirmed.last_observed_at == "2026-05-28T02:00:00Z"
    assert qa_confirmed.evidence_sources == [
        CapabilityEvidenceSource.DECLARED,
        CapabilityEvidenceSource.QA_CONFIRMED,
    ]

    explicit = directory.record_capability_evidence(
        "qa",
        "pytest",
        "observed",
        confidence=0.99,
    )
    assert explicit.confidence == pytest.approx(0.99)
    assert CapabilityEvidenceSource.OBSERVED in explicit.evidence_sources

    clamped = directory.record_capability_evidence(
        "qa",
        "pytest",
        "user_assigned",
        confidence=2.0,
    )
    assert clamped.confidence == pytest.approx(1.0)


def test_replace_session_marks_old_session_replaced_and_activates_replacement():
    directory = AgentDirectory()
    directory.register_identity("worker.docs")
    old = directory.start_session("worker.docs", session_id="old")
    replacement = directory.start_session("worker.docs", session_id="replacement", activate=False)

    replaced, activated = directory.replace_session(old.session_id, replacement.session_id)

    assert replaced.session_id == "old"
    assert replaced.active is False
    assert replaced.runtime_state is AgentRuntimeState.REPLACED
    assert replaced.replaced_by_session_id == "replacement"
    assert replaced.ended_at is not None
    assert activated.session_id == "replacement"
    assert activated.active is True
    assert directory.get_active_session("worker.docs").session_id == "replacement"
    assert directory.get_health("old").health_score == 0.0


def test_update_session_state_tracks_input_unavailable_health():
    directory = AgentDirectory()
    directory.register_identity("worker.cli")
    session = directory.start_session("worker.cli", session_id="cli-session")

    health = directory.update_session_state(
        session.session_id,
        AgentRuntimeState.INPUT_UNAVAILABLE,
        reason="terminal prompt closed",
    )

    assert health.runtime_state is AgentRuntimeState.INPUT_UNAVAILABLE
    assert health.input_available is False
    assert health.stale is True
    assert health.reason == "terminal prompt closed"


def test_heartbeat_session_refreshes_last_seen_and_preserves_state():
    directory = AgentDirectory()
    directory.register_identity("worker.cli")
    session = directory.start_session("worker.cli", session_id="cli-session")
    session.last_seen_at = "2026-05-28T00:00:00Z"

    health = directory.heartbeat_session(session.session_id, reason="poll alive")

    assert directory.get_session(session.session_id).runtime_state is AgentRuntimeState.STANDBY_READY
    assert directory.get_session(session.session_id).last_seen_at != "2026-05-28T00:00:00Z"
    assert health.runtime_state is AgentRuntimeState.STANDBY_READY
    assert health.stale is False
    assert health.reason == "poll alive"


def test_heartbeat_session_can_update_runtime_state():
    directory = AgentDirectory()
    directory.register_identity("worker.cli")
    session = directory.start_session("worker.cli", session_id="cli-session")

    health = directory.heartbeat_session(
        session.session_id,
        runtime_state=AgentRuntimeState.WORKING,
        reason="still building",
    )

    assert directory.get_session(session.session_id).runtime_state is AgentRuntimeState.WORKING
    assert health.runtime_state is AgentRuntimeState.WORKING
    assert health.reason == "still building"


def test_unknown_identity_and_session_operations_raise_clear_errors():
    directory = AgentDirectory()

    with pytest.raises(AgentDirectoryError, match="unknown agent identity"):
        directory.start_session("missing")

    directory.register_identity("worker")
    with pytest.raises(AgentDirectoryError, match="unknown agent session"):
        directory.switch_active_session("worker", "missing-session")

    directory.register_identity("other")
    session = directory.start_session("other")
    with pytest.raises(AgentDirectoryError, match="does not belong"):
        directory.switch_active_session("worker", session.session_id)
