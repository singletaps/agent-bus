from __future__ import annotations

from agent_bus.authority import controller_principal
from agent_bus.context import ContextStore
from agent_bus.gates import GateBoard
from agent_bus.models import BusEvent, EventType
from agent_bus.projections import build_operations_projection
from agent_bus.protocol import ProtocolKernel
from agent_bus.protocol_models import FencingResult
from agent_bus.store import EventStore
from agent_bus.tasks import TaskBoard


def test_task_workflow_contains_task_bound_protocol_nodes(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    principal = controller_principal()
    tasks = TaskBoard(db_path=db_path, principal=principal)
    run = tasks.create_run("Wave4", created_by="controller")
    task = tasks.create_task("Projection contract", run_id=run.run_id, owner_agent_id="controller")
    packet = ContextStore(db_path, principal=principal).create_packet(
        agent_id="runtime-worker-5",
        task_id=task.task_id,
        run_id=run.run_id,
        summary="Projection scope packet",
        actor="controller",
    )
    gate = GateBoard(db_path=db_path, principal=principal).create_gate(
        "Projection QA",
        run_id=run.run_id,
        task_id=task.task_id,
        requested_by="runtime-worker-5",
    )
    artifact = tasks.create_artifact(
        "projection-report",
        "coordination/projection-report.txt",
        run_id=run.run_id,
        task_id=task.task_id,
        created_by="runtime-worker-5",
    )
    EventStore(db_path).append_event(
        BusEvent(
            type=EventType.TASK_COMPLETION_CLAIMED,
            actor="runtime-worker-5",
            run_id=run.run_id,
            task_id=task.task_id,
            payload={"task_id": task.task_id, "claim_kind": "completion"},
        )
    )
    EventStore(db_path).append_event(
        BusEvent(
            type=EventType.REPLACEMENT_RECOMMENDED,
            actor="runtime-helper-2",
            run_id=run.run_id,
            task_id=task.task_id,
            payload={"recommendation_id": "rec-1", "task_id": task.task_id},
        )
    )

    workflow = build_operations_projection(db_path).ui.task_workflow
    nodes_by_kind = {node.kind: node for node in workflow.nodes}

    assert workflow.task_ids == [task.task_id]
    assert nodes_by_kind["context"].task_id == task.task_id
    assert nodes_by_kind["context"].context_packet_id == packet.packet_id
    assert nodes_by_kind["claim"].task_id == task.task_id
    assert nodes_by_kind["gate"].gate_id == gate.gate_id
    assert nodes_by_kind["artifact"].artifact_id == artifact.artifact_id
    assert nodes_by_kind["replacement"].task_id == task.task_id
    assert all(edge.task_id in {"", task.task_id} for edge in workflow.edges)


def test_task_workflow_drops_cross_task_edges_and_records_projection_violation(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    principal = controller_principal()
    tasks = TaskBoard(db_path=db_path, principal=principal)
    run = tasks.create_run("Wave4", created_by="controller")
    first = tasks.create_task("First", run_id=run.run_id, owner_agent_id="controller")
    second = tasks.create_task("Second", run_id=run.run_id, owner_agent_id="controller")
    EventStore(db_path).append_event(
        BusEvent(
            type=EventType.TASK_PROGRESS_REPORTED,
            actor="runtime-worker-5",
            run_id=run.run_id,
            task_id=first.task_id,
            payload={"task_id": second.task_id, "summary": "malformed cross-task edge"},
        )
    )
    EventStore(db_path).append_event(
        BusEvent(
            type=EventType.COORDINATION_RECORDED,
            actor="controller",
            run_id=run.run_id,
            payload={"summary": "run-global event"},
        )
    )

    workflow = build_operations_projection(db_path).ui.task_workflow

    assert {node.task_id for node in workflow.nodes if node.kind == "task"} == {first.task_id, second.task_id}
    assert not any(node.kind == "claim" for node in workflow.nodes)
    assert not any(edge.source.startswith("event:") or edge.target.startswith("event:") for edge in workflow.edges)
    assert workflow.diagnostics
    assert workflow.diagnostics[0].kind == "protocol_violation"
    assert "cross-task" in workflow.diagnostics[0].detail


def test_projection_surfaces_protocol_effects_and_rejections(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    ProtocolKernel(db_path).reject_action(
        action="gate.approved",
        actor="runtime-worker-5",
        actor_role="worker",
        reason="worker cannot approve gate",
        fencing_result=FencingResult.NOT_REQUIRED,
        payload={"gate_id": "gate-1"},
        task_id="task-1",
    )

    diagnostics = build_operations_projection(db_path).ui.diagnostics

    assert diagnostics.protocol_violations[0].kind == "protocol_violation"
    assert diagnostics.protocol_violations[0].detail == "worker cannot approve gate"
    assert diagnostics.projection_effects[0].effect == "REJECT"
