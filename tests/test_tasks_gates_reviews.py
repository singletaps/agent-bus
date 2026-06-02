from __future__ import annotations

import pytest

from agent_bus.agents import AgentDirectory
from agent_bus.authority import controller_principal
from agent_bus.gates import GateBoard
from agent_bus.inbox import InboxStore
from agent_bus.models import AgentRuntimeState, GateState, ReviewFindingStatus, TaskState
from agent_bus.reviews import ReviewBoard
from agent_bus.store import EventStore
from agent_bus.tasks import TaskBoard


def test_direct_task_completion_is_guarded_and_records_only_non_terminal_progress(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("worker.backend")
    directory.start_session("worker.backend", session_id="session-backend")
    board = TaskBoard(db_path=db_path, agent_directory=directory, principal=controller_principal())

    run = board.create_run("Wave B runtime semantics", created_by="controller")
    task = board.create_task("Implement task state machine", run_id=run.run_id, owner_agent_id="controller")
    assigned = board.assign_task(task.task_id, "worker.backend", actor="controller")
    acknowledged = board.acknowledge_task(assigned.task_id, actor="worker.backend")
    working = board.start_task(acknowledged.task_id, actor="worker.backend")

    with pytest.raises(PermissionError, match="direct authoritative mutator is forbidden"):
        board.complete_task(working.task_id, actor="worker.backend")

    guarded = board.get_task(working.task_id)
    assert [state.status for state in [assigned, acknowledged, working, guarded]] == [
        TaskState.ASSIGNED,
        TaskState.ACKNOWLEDGED,
        TaskState.WORKING,
        TaskState.WORKING,
    ]
    assert guarded.completed_at is None
    assert directory.get_health("session-backend").runtime_state is AgentRuntimeState.WORKING

    events = EventStore(db_path).query_events(task_id=task.task_id)
    assert [event.type for event in events] == [
        "task.created",
        "task.assigned",
        "context.created",
        "task.acknowledged",
        "task.progress",
    ]

    blocked = board.block_task(task.task_id, "guard leaves non-terminal work blockable", actor="worker.backend")
    assert blocked.status is TaskState.BLOCKED


def test_changes_requested_creates_worker_inbox_item_and_findings_resolve_one_by_one(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    reviews = ReviewBoard(db_path=db_path)

    findings = reviews.request_changes(
        run_id="run-1",
        task_id="task-1",
        worker_agent_id="worker.frontend",
        reviewer_agent_id="qa",
        findings=[
            {
                "severity": "P1",
                "category": "behavior",
                "file_path": "frontend/src/App.tsx",
                "evidence": "task board does not render blocked tasks",
                "requested_change": "render blocked tasks in the attention lane",
                "blocking": True,
            },
            {
                "severity": "P2",
                "category": "test",
                "file_path": "tests/test_tasks_gates_reviews.py",
                "evidence": "no finding resolution coverage",
                "requested_change": "add one-by-one resolution coverage",
                "blocking": False,
            },
        ],
    )

    inbox_items = InboxStore(db_path).list_items("worker.frontend")
    assert len(findings) == 2
    assert [finding.status for finding in findings] == [
        ReviewFindingStatus.OPEN,
        ReviewFindingStatus.OPEN,
    ]
    assert inbox_items[0].kind == "changes_requested"
    assert inbox_items[0].priority == 80
    assert inbox_items[0].payload["finding_ids"] == [finding.finding_id for finding in findings]

    resolved = reviews.resolve_finding(findings[0].finding_id, resolved_by="worker.frontend")

    assert resolved.status is ReviewFindingStatus.RESOLVED
    assert resolved.resolved_by == "worker.frontend"
    assert reviews.get_finding(findings[1].finding_id).status is ReviewFindingStatus.OPEN
    assert len(reviews.list_findings(task_id="task-1", status=ReviewFindingStatus.OPEN)) == 1


def test_high_risk_gate_escalates_and_enqueues_controller_action_before_approval(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    gates = GateBoard(db_path=db_path, principal=controller_principal())
    gate = gates.create_gate(
        "Replacement approval",
        run_id="run-1",
        task_id="task-1",
        owner_agent_id="qa",
        requested_by="qa",
        risk="high",
    )

    escalated = gates.approve_gate(gate.gate_id, actor="qa", action_agent_id="controller")

    assert escalated.state is GateState.ESCALATED
    assert gates.get_gate(gate.gate_id).state is GateState.ESCALATED
    controller_items = InboxStore(db_path).list_items("controller")
    assert len(controller_items) == 1
    assert controller_items[0].kind == "gate_approval_required"
    assert controller_items[0].payload["gate_id"] == gate.gate_id

    approved = gates.approve_gate(gate.gate_id, actor="controller")
    assert approved.state is GateState.APPROVED
    assert approved.resolved_at is not None


def test_lease_and_intent_are_coordination_records_not_permission_enforcement(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    board = TaskBoard(db_path=db_path, principal=controller_principal())
    task = board.create_task("Write docs", owner_agent_id="controller")

    lease = board.record_coordination(
        "lease",
        task_id=task.task_id,
        agent_id="worker.docs",
        payload={"scope": ["README.md"]},
    )
    intent = board.record_coordination(
        "intent",
        task_id=task.task_id,
        agent_id="worker.frontend",
        payload={"action": "complete despite different lease holder"},
    )

    assigned = board.assign_task(task.task_id, "worker.frontend", actor="controller")
    board.acknowledge_task(assigned.task_id, actor="worker.frontend")
    board.start_task(assigned.task_id, actor="worker.frontend")
    with pytest.raises(PermissionError, match="direct authoritative mutator is forbidden"):
        board.complete_task(assigned.task_id, actor="worker.frontend")

    assert board.get_task(assigned.task_id).status is TaskState.WORKING
    assert [record.record_id for record in board.list_coordination_records(task.task_id)] == [
        lease.record_id,
        intent.record_id,
    ]


def test_artifacts_are_durable_and_linked_to_task_events(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    board = TaskBoard(db_path=db_path, principal=controller_principal())
    artifact = board.create_artifact(
        "test-log",
        "coordination/test-output.txt",
        run_id="run-1",
        task_id="task-1",
        metadata={"passed": 22},
        created_by="qa",
    )

    events = EventStore(db_path).query_events(event_type="artifact.created", task_id="task-1")

    assert artifact.metadata == {"passed": 22}
    assert events[0].payload["artifact_id"] == artifact.artifact_id
