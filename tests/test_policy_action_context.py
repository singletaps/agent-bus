from __future__ import annotations

from agent_bus.authority import controller_principal
from agent_bus.context import ContextStore
from agent_bus.policy import PolicyService
from agent_bus.protocol_models import PacketKind


def test_worker_actions_require_active_task_context_binding(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    policy = PolicyService(db_path)

    missing = policy.evaluate(
        action="task.progress_reported",
        agent_id="worker.backend",
        task_id="task-1",
        session_id="session-worker",
        context_packet_id=None,
    )

    assert missing.allowed is False
    assert "context" in (missing.reason or "")


def test_worker_context_policy_checks_task_agent_and_session_binding(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    packet = ContextStore(db_path, principal=controller_principal()).create_packet(
        agent_id="worker.backend",
        task_id="task-1",
        run_id="run-1",
        summary="Assignment",
        actor="controller",
        session_id="session-worker",
        session_epoch=3,
        packet_kind=PacketKind.ASSIGNMENT,
    )
    policy = PolicyService(db_path)

    allowed = policy.evaluate(
        action="task.progress_reported",
        agent_id="worker.backend",
        task_id="task-1",
        session_id="session-worker",
        context_packet_id=packet.packet_id,
    )
    wrong_agent = policy.evaluate(
        action="task.progress_reported",
        agent_id="worker.other",
        task_id="task-1",
        session_id="session-worker",
        context_packet_id=packet.packet_id,
    )
    controller_optional = policy.evaluate(action="task.assigned", task_id="task-1", context_packet_id=None)

    assert allowed.allowed is True
    assert wrong_agent.allowed is False
    assert "agent" in (wrong_agent.reason or "")
    assert controller_optional.allowed is True


def test_context_creation_remains_context_optional(tmp_path):
    decision = PolicyService(tmp_path / "agent-bus.sqlite3").evaluate(
        action="context.created",
        agent_id="worker.backend",
        task_id="task-1",
        context_packet_id=None,
    )

    assert decision.allowed is True
