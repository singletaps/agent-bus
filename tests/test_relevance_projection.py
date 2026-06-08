from __future__ import annotations

import pytest

from agent_bus.models import (
    AgentHealth,
    AgentIdentity,
    AgentRuntimeState,
    AgentSession,
    ArtifactRecord,
    ContextPacket,
    GateRecord,
    GateState,
    InboxItem,
    RunRecord,
    RunState,
    TaskRecord,
    TaskState,
)
from agent_bus.projections import AgentProjection
from agent_bus.relevance import derive_relevance_projection


def _active_run() -> RunRecord:
    return RunRecord(run_id="run-relevance", title="Relevance", status=RunState.ACTIVE)


def _task(
    task_id: str = "task-current",
    *,
    run_id: str = "run-relevance",
    status: TaskState = TaskState.WORKING,
    owner_agent_id: str | None = "worker",
    assignee_agent_id: str | None = None,
) -> TaskRecord:
    return TaskRecord(
        task_id=task_id,
        run_id=run_id,
        title=task_id,
        owner_agent_id=owner_agent_id,
        assignee_agent_id=assignee_agent_id,
        status=status,
    )


def _agent(
    agent_id: str = "worker",
    *,
    role: str = "worker",
    runtime_state: AgentRuntimeState = AgentRuntimeState.STANDBY_READY,
    stale: bool = False,
    with_session: bool = True,
) -> AgentProjection:
    session = (
        AgentSession(
            session_id=f"session-{agent_id}",
            agent_id=agent_id,
            session_role="primary",
            runtime_state=runtime_state,
            last_seen_at="2026-06-04T08:00:00Z",
        )
        if with_session
        else None
    )
    health = (
        AgentHealth(
            agent_id=agent_id,
            session_id=session.session_id,
            runtime_state=runtime_state,
            stale=stale,
        )
        if session is not None
        else None
    )
    return AgentProjection(
        identity=AgentIdentity(agent_id=agent_id, role=role),
        active_session=session,
        health=health,
    )


def test_gate_on_terminal_task_is_historical_not_actionable(tmp_path):
    run = _active_run()
    completed_task = _task("task-done", run_id=run.run_id, status=TaskState.COMPLETED)
    gate = GateRecord(
        gate_id="gate-old-qa",
        name="Old QA",
        run_id=run.run_id,
        task_id=completed_task.task_id,
        requested_by="worker",
    )

    relevance = derive_relevance_projection(
        active_run=run,
        runs=[run],
        tasks=[completed_task],
        gates=[gate],
        artifacts=[],
        agents=[],
        contexts=[],
        inbox=[],
    )

    gate_relevance = relevance.gates[gate.gate_id]
    assert gate_relevance.relevance_state == "historical"
    assert gate_relevance.visible_in_approval_center is False
    assert gate_relevance.reason == "task_terminal"


def test_newer_same_task_kind_gate_supersedes_older_gate():
    run = _active_run()
    task = _task(run_id=run.run_id)
    older = GateRecord(
        gate_id="gate-older",
        name="Old QA",
        run_id=run.run_id,
        task_id=task.task_id,
        gate_kind="qa",
        created_at="2026-06-04T08:00:00Z",
    )
    newer = GateRecord(
        gate_id="gate-newer",
        name="New QA",
        run_id=run.run_id,
        task_id=task.task_id,
        gate_kind="qa",
        created_at="2026-06-04T08:01:00Z",
    )

    relevance = derive_relevance_projection(
        active_run=run,
        runs=[run],
        tasks=[task],
        gates=[older, newer],
        artifacts=[],
        agents=[],
        contexts=[],
        inbox=[],
    )

    assert relevance.gates[older.gate_id].relevance_state == "superseded"
    assert relevance.gates[older.gate_id].superseded_by_gate_id == newer.gate_id
    assert relevance.gates[older.gate_id].visible_in_approval_center is False
    assert relevance.gates[newer.gate_id].relevance_state == "actionable"
    assert relevance.gates[newer.gate_id].visible_in_approval_center is True


@pytest.mark.parametrize("state", [GateState.REJECTED, GateState.APPROVED, GateState.EXPIRED])
def test_resolved_gate_states_are_historical(state: GateState):
    run = _active_run()
    task = _task(run_id=run.run_id)
    gate = GateRecord(
        gate_id=f"gate-{state.value}",
        name=f"{state.value} gate",
        run_id=run.run_id,
        task_id=task.task_id,
        state=state,
    )

    relevance = derive_relevance_projection(
        active_run=run,
        runs=[run],
        tasks=[task],
        gates=[gate],
        artifacts=[],
        agents=[],
        contexts=[],
        inbox=[],
    )

    assert relevance.gates[gate.gate_id].relevance_state == "historical"
    assert relevance.gates[gate.gate_id].visible_in_approval_center is False
    assert relevance.gates[gate.gate_id].reason == "gate_resolved"


def test_stale_agent_with_no_responsibility_is_archived():
    agent = _agent(runtime_state=AgentRuntimeState.STANDBY_DEGRADED, stale=True)

    relevance = derive_relevance_projection(
        active_run=None,
        runs=[],
        tasks=[],
        gates=[],
        artifacts=[],
        agents=[agent],
        contexts=[],
        inbox=[],
    )

    projected = relevance.agents["worker"]
    assert projected.identity_state == "archived"
    assert projected.online_state == "stale"
    assert projected.visible_in_main is False
    assert projected.hidden_reason == "stale_without_responsibility"
    assert relevance.hidden_counts.archived_agents == 1
    assert relevance.hidden_counts.stale_sessions == 1


def test_stale_agent_with_active_task_stays_visible():
    run = _active_run()
    task = _task(run_id=run.run_id, assignee_agent_id="worker")
    agent = _agent(runtime_state=AgentRuntimeState.STANDBY_DEGRADED, stale=True)

    relevance = derive_relevance_projection(
        active_run=run,
        runs=[run],
        tasks=[task],
        gates=[],
        artifacts=[],
        agents=[agent],
        contexts=[],
        inbox=[],
    )

    projected = relevance.agents["worker"]
    assert projected.identity_state == "active"
    assert projected.online_state == "stale"
    assert projected.current_task_id == task.task_id
    assert projected.visible_in_main is True
    assert projected.hidden_reason is None


def test_queued_inbox_makes_agent_visible():
    agent = _agent()
    inbox_item = InboxItem(inbox_id="inbox-worker", agent_id="worker", kind="task_assigned", status="queued")

    relevance = derive_relevance_projection(
        active_run=None,
        runs=[],
        tasks=[],
        gates=[],
        artifacts=[],
        agents=[agent],
        contexts=[],
        inbox=[inbox_item],
    )

    projected = relevance.agents["worker"]
    assert projected.visible_in_main is True
    assert projected.work_state == "waiting_input"
    assert projected.queued_inbox == 1


def test_replaced_agent_queued_inbox_does_not_keep_agent_visible():
    agent = _agent(agent_id="sim2-frontend", runtime_state=AgentRuntimeState.REPLACED)
    inbox_item = InboxItem(
        inbox_id="inbox-sim2-frontend",
        agent_id="sim2-frontend",
        kind="replacement_notice",
        status="queued",
    )

    relevance = derive_relevance_projection(
        active_run=None,
        runs=[],
        tasks=[],
        gates=[],
        artifacts=[],
        agents=[agent],
        contexts=[],
        inbox=[inbox_item],
    )

    projected = relevance.agents["sim2-frontend"]
    assert projected.identity_state == "archived"
    assert projected.visible_in_main is False
    assert projected.queued_inbox == 0


def test_gate_waiting_owner_when_decision_owner_stale():
    run = _active_run()
    task = _task(run_id=run.run_id, owner_agent_id="worker")
    gate = GateRecord(
        gate_id="gate-wait-owner",
        name="Owner unavailable",
        run_id=run.run_id,
        task_id=task.task_id,
        owner_agent_id="runtime-qa",
    )
    stale_owner = _agent(
        agent_id="runtime-qa",
        role="qa",
        runtime_state=AgentRuntimeState.STANDBY_DEGRADED,
        stale=True,
    )

    relevance = derive_relevance_projection(
        active_run=run,
        runs=[run],
        tasks=[task],
        gates=[gate],
        artifacts=[],
        agents=[stale_owner],
        contexts=[],
        inbox=[],
    )

    gate_relevance = relevance.gates[gate.gate_id]
    assert gate_relevance.relevance_state == "waiting_owner"
    assert gate_relevance.visibility == "needs_attention"
    assert gate_relevance.visible_in_approval_center is False


def test_gate_waiting_evidence_when_required_artifact_missing():
    run = _active_run()
    task = _task(run_id=run.run_id)
    gate = GateRecord(
        gate_id="gate-wait-evidence",
        name="Evidence required",
        run_id=run.run_id,
        task_id=task.task_id,
        required_evidence=["artifact-required"],
    )

    relevance = derive_relevance_projection(
        active_run=run,
        runs=[run],
        tasks=[task],
        gates=[gate],
        artifacts=[],
        agents=[],
        contexts=[],
        inbox=[],
    )

    gate_relevance = relevance.gates[gate.gate_id]
    assert gate_relevance.relevance_state == "waiting_evidence"
    assert gate_relevance.visible_in_approval_center is False


def test_ownerless_open_gate_remains_actionable():
    run = _active_run()
    task = _task(run_id=run.run_id)
    gate = GateRecord(
        gate_id="gate-ownerless",
        name="Ownerless approval",
        run_id=run.run_id,
        task_id=task.task_id,
        requested_by="worker",
    )

    relevance = derive_relevance_projection(
        active_run=run,
        runs=[run],
        tasks=[task],
        gates=[gate],
        artifacts=[],
        agents=[],
        contexts=[],
        inbox=[],
    )

    gate_relevance = relevance.gates[gate.gate_id]
    assert gate_relevance.relevance_state == "actionable"
    assert gate_relevance.visible_in_approval_center is True


def test_active_task_is_visible_on_home_and_completed_task_is_hidden():
    run = _active_run()
    active = _task("task-active", run_id=run.run_id, status=TaskState.WORKING)
    completed = _task("task-completed", run_id=run.run_id, status=TaskState.COMPLETED)

    relevance = derive_relevance_projection(
        active_run=run,
        runs=[run],
        tasks=[active, completed],
        gates=[],
        artifacts=[],
        agents=[],
        contexts=[],
        inbox=[],
    )

    assert relevance.tasks[active.task_id].lifecycle_state == "active"
    assert relevance.tasks[active.task_id].visible_in_home is True
    assert relevance.tasks[active.task_id].visible_in_rungraph is True
    assert relevance.tasks[completed.task_id].lifecycle_state == "terminal"
    assert relevance.tasks[completed.task_id].visible_in_home is False
    assert relevance.tasks[completed.task_id].hidden_reason == "task_terminal"


def test_artifact_without_run_or_task_is_legacy_unbound():
    artifact = ArtifactRecord(artifact_id="artifact-unbound", kind="log", uri="coordination/unbound.txt")

    relevance = derive_relevance_projection(
        active_run=None,
        runs=[],
        tasks=[],
        gates=[],
        artifacts=[artifact],
        agents=[],
        contexts=[],
        inbox=[],
    )

    projected = relevance.artifacts[artifact.artifact_id]
    assert projected.visibility == "legacy_unbound"
    assert projected.visible_in_default_list is False
    assert projected.reason == "unbound_artifact"
    assert relevance.hidden_counts.unbound_artifacts == 1


def test_context_hidden_count_keeps_latest_active_context_visible():
    run = _active_run()
    task = _task(run_id=run.run_id)
    invalidated = ContextPacket(
        packet_id="ctx-invalidated",
        agent_id="worker",
        task_id=task.task_id,
        run_id=run.run_id,
        status="invalidated",
        created_at="2026-06-04T08:00:00Z",
    )
    superseded = ContextPacket(
        packet_id="ctx-superseded",
        agent_id="worker",
        task_id=task.task_id,
        run_id=run.run_id,
        status="superseded",
        created_at="2026-06-04T08:01:00Z",
    )
    active = ContextPacket(
        packet_id="ctx-active",
        agent_id="worker",
        task_id=task.task_id,
        run_id=run.run_id,
        status="active",
        created_at="2026-06-04T08:02:00Z",
    )

    relevance = derive_relevance_projection(
        active_run=run,
        runs=[run],
        tasks=[task],
        gates=[],
        artifacts=[],
        agents=[],
        contexts=[invalidated, superseded, active],
        inbox=[],
    )

    assert relevance.hidden_counts.hidden_context_packets == 2
    context_clusters = relevance.workflow_clusters[task.task_id]
    assert context_clusters[0].kind == "context_history"
    assert context_clusters[0].count == 2
    assert set(context_clusters[0].node_ids) == {invalidated.packet_id, superseded.packet_id}
    assert active.packet_id not in context_clusters[0].node_ids
