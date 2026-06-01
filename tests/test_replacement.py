from __future__ import annotations

from datetime import datetime, timezone

from agent_bus.agents import AgentDirectory
from agent_bus.context import ContextStore
from agent_bus.inbox import InboxStore
from agent_bus.models import AgentRuntimeState, CapabilityEvidenceSource
from agent_bus.replacement import ReplacementCoordinator


def _directory_with_candidate() -> tuple[AgentDirectory, object, object]:
    directory = AgentDirectory()
    directory.register_identity("worker.frontend", role="worker", declared_capabilities=["react"])
    old = directory.start_session("worker.frontend", run_id="run_1", session_id="old-session")
    directory.register_identity("runtime-helper-1", role="worker", declared_capabilities=["react"])
    replacement = directory.start_session(
        "runtime-helper-1",
        run_id="run_1",
        session_id="helper-session",
        runtime_state=AgentRuntimeState.STANDBY_READY,
    )
    directory.record_capability_evidence(
        "runtime-helper-1",
        "react",
        CapabilityEvidenceSource.QA_CONFIRMED,
    )
    return directory, old, replacement


def test_context_loss_input_unavailable_and_manual_mark_produce_recommendations():
    directory, old, _replacement = _directory_with_candidate()
    coordinator = ReplacementCoordinator(directory=directory)

    directory.report_context_loss(old.session_id, reason="context compression failed")
    context_loss = coordinator.recommend_for_session(
        old.session_id,
        task_id="task-ui",
        required_capabilities=("react",),
        now=datetime.now(timezone.utc),
    )
    assert context_loss is not None
    assert "context_suspect" in {trigger.name for trigger in context_loss.triggers}

    directory.update_session_state(old.session_id, AgentRuntimeState.INPUT_UNAVAILABLE, reason="stdin closed")
    input_unavailable = coordinator.recommend_for_session(old.session_id, task_id="task-ui")
    assert input_unavailable is not None
    assert "input_unavailable" in {trigger.name for trigger in input_unavailable.triggers}

    directory.update_session_state(old.session_id, AgentRuntimeState.SUSPECTED_STUCK, reason="controller mark")
    manual = coordinator.recommend_for_session(old.session_id, task_id="task-ui")
    assert manual is not None
    assert "manual_controller_mark" in {trigger.name for trigger in manual.triggers}


def test_missing_heartbeat_and_delivered_not_acked_are_replacement_triggers():
    directory, old, _replacement = _directory_with_candidate()
    directory.update_session_state(old.session_id, AgentRuntimeState.DELIVERED_NOT_ACKED)
    directory.get_session(old.session_id).last_seen_at = "2026-05-28T00:00:00Z"
    coordinator = ReplacementCoordinator(directory=directory, heartbeat_timeout_seconds=60)

    recommendation = coordinator.recommend_for_session(
        old.session_id,
        task_id="task-api",
        now=datetime(2026, 5, 28, 1, 0, tzinfo=timezone.utc),
    )

    assert recommendation is not None
    trigger_names = {trigger.name for trigger in recommendation.triggers}
    assert {"missing_heartbeat", "delivered_not_acked"} <= trigger_names


def test_candidate_scoring_prefers_capable_standby_role_match():
    directory, old, _replacement = _directory_with_candidate()
    directory.register_identity("runtime-helper-2", role="observer", declared_capabilities=["react"])
    directory.start_session(
        "runtime-helper-2",
        session_id="helper-2-session",
        runtime_state=AgentRuntimeState.STANDBY_READY,
    )
    directory.record_capability_evidence(
        "runtime-helper-2",
        "react",
        CapabilityEvidenceSource.USER_ASSIGNED,
        confidence=0.99,
    )
    directory.report_context_loss(old.session_id)
    coordinator = ReplacementCoordinator(directory=directory)

    recommendation = coordinator.recommend_for_session(
        old.session_id,
        task_id="task-ui",
        required_capabilities=("react",),
        role="worker",
    )

    assert recommendation is not None
    assert recommendation.candidate.agent_id == "runtime-helper-1"
    assert recommendation.candidate.score > 0.7


def test_controller_approval_switches_replacement_and_rehydrates_same_task(tmp_path):
    db_path = tmp_path / "bus.sqlite3"
    directory, old, replacement = _directory_with_candidate()
    directory.report_context_loss(old.session_id, reason="lost context")
    inbox = InboxStore(db_path)
    inbox.enqueue("worker.frontend", "task_assigned", {"task_id": "task-ui"})
    context_sink = ContextStore(db_path)
    coordinator = ReplacementCoordinator(directory=directory, inbox=inbox, context_sink=context_sink)
    recommendation = coordinator.recommend_for_session(
        old.session_id,
        task_id="task-ui",
        run_id="run_1",
        required_capabilities=("react",),
        role="worker",
    )

    approval = coordinator.approve(
        recommendation,
        approved_by="controller",
        required_artifacts=("artifact://diff",),
        next_action="continue implementation",
    )

    assert approval.task_id == "task-ui"
    assert approval.context_packet.task_id == "task-ui"
    assert approval.context_packet.agent_id == "runtime-helper-1"
    assert approval.context_packet.instructions["current_task"] == "task-ui"
    assert approval.context_packet.instructions["role_contract"] == "replacement for worker.frontend"
    assert approval.context_packet.instructions["next_action"] == "continue implementation"
    assert approval.context_packet.instructions["required_artifacts"] == ["artifact://diff"]
    assert approval.context_packet.instructions["open_inbox_item_ids"]
    assert context_sink.get_packet(approval.context_packet.packet_id) == approval.context_packet

    old_after = directory.get_session(old.session_id)
    replacement_after = directory.get_session(replacement.session_id)
    assert old_after.runtime_state is AgentRuntimeState.REPLACED
    assert old_after.replaced_by_session_id == replacement.session_id
    assert replacement_after.active is True
    assert replacement_after.runtime_state is AgentRuntimeState.REHYDRATING

    notice = inbox.wait("runtime-helper-1", timeout=0.1).item
    assert notice.kind == "replacement_notice"
    assert notice.context_packet_id == approval.context_packet.packet_id
    assert notice.payload["task_id"] == "task-ui"
