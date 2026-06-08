from agent_bus.agents import AgentDirectory
from agent_bus.models import (
    AgentIdentityLifecycle,
    AgentRuntimeState,
    IdentityOrigin,
    PresenceState,
    RuntimeCondition,
    SessionEndReason,
    UIVisibilityState,
    VisibilityPolicy,
)
from agent_bus.protocol_models import SessionRole


def test_identity_target_metadata_defaults_and_round_trips(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    identity = directory.register_identity("sim2-qa", role="qa", display_name="Sim2 QA")

    assert identity.identity_lifecycle is AgentIdentityLifecycle.ACTIVE
    assert identity.identity_origin is IdentityOrigin.RUNTIME_DISCOVERED
    assert identity.visibility_policy is VisibilityPolicy.NORMAL
    assert identity.canonical is False
    assert identity.archive_reason is None

    reloaded = AgentDirectory(db_path=db_path).get_identity("sim2-qa")
    assert reloaded.identity_lifecycle is AgentIdentityLifecycle.ACTIVE
    assert reloaded.identity_origin is IdentityOrigin.RUNTIME_DISCOVERED
    assert reloaded.visibility_policy is VisibilityPolicy.NORMAL
    assert reloaded.canonical is False


def test_session_end_reason_round_trips(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("worker")
    session = directory.start_session("worker", session_id="session-worker")

    directory.retire_session(
        session.session_id,
        end_reason=SessionEndReason.EXPIRED,
        reason="heartbeat expired with no responsibility",
    )

    reloaded = AgentDirectory(db_path=db_path).get_session(session.session_id)
    assert reloaded.active is False
    assert reloaded.session_role is SessionRole.RETIRED
    assert reloaded.session_end_reason is SessionEndReason.EXPIRED
    assert reloaded.ended_at is not None


def test_retire_session_removes_primary_write_authority(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("worker")
    session = directory.start_session("worker", session_id="session-worker")

    assert session.active is True
    assert session.session_role is SessionRole.PRIMARY

    directory.retire_session(
        session.session_id,
        end_reason=SessionEndReason.RETIRED,
        reason="manual retire",
    )

    reloaded = AgentDirectory(db_path=db_path).get_session(session.session_id)
    assert reloaded.active is False
    assert reloaded.session_role is SessionRole.RETIRED
    assert reloaded.session_end_reason is SessionEndReason.RETIRED


def test_runtime_condition_contract_is_stable():
    condition = RuntimeCondition(
        type="Reachable",
        status="false",
        reason="missing_heartbeat",
        message="last heartbeat exceeded hard timeout",
        severity="warning",
        source="runtime_state_policy",
    )

    dumped = condition.model_dump(mode="json")
    assert dumped["type"] == "Reachable"
    assert dumped["status"] == "false"
    assert dumped["severity"] == "warning"
    assert dumped["source"] == "runtime_state_policy"


def test_session_authority_uses_session_role_and_replacement_end_reason(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("worker")
    old = directory.start_session("worker", session_id="old")
    replacement = directory.start_session("worker", session_id="replacement", activate=False)

    assert old.session_role is SessionRole.PRIMARY
    assert replacement.session_role is SessionRole.STANDBY

    directory.replace_session(old.session_id, replacement.session_id)
    reloaded = AgentDirectory(db_path=db_path)
    replaced = reloaded.get_session(old.session_id)
    activated = reloaded.get_session(replacement.session_id)

    assert replaced.runtime_state is AgentRuntimeState.REPLACED
    assert replaced.session_role is SessionRole.REPLACED
    assert replaced.session_end_reason is SessionEndReason.REPLACED
    assert replaced.replaced_by_session_id == replacement.session_id
    assert activated.active is True
    assert activated.session_role is SessionRole.PRIMARY


def test_projection_enum_values_match_target_doc():
    assert PresenceState.ONLINE.value == "online"
    assert PresenceState.STALE.value == "stale"
    assert PresenceState.OFFLINE.value == "offline"
    assert UIVisibilityState.NEEDS_ATTENTION.value == "needs_attention"
