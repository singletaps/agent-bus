from __future__ import annotations

from agent_bus.authority import controller_principal
from agent_bus.context import ContextStore
from agent_bus.gates import GateBoard
from agent_bus.models import BusEvent, EventType
from agent_bus.projections import build_operations_projection
from agent_bus.store import EventStore
from agent_bus.tasks import TaskBoard


def test_ui_task_workflows_are_keyed_by_task_and_do_not_chain_tasks(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    principal = controller_principal()
    tasks = TaskBoard(db_path=db_path, principal=principal)
    run = tasks.create_run("Wave7", objective="Task-scoped workflow", created_by="controller")
    first = tasks.create_task("Frontend graph", run_id=run.run_id, owner_agent_id="controller")
    second = tasks.create_task("Backend API", run_id=run.run_id, owner_agent_id="controller")
    ContextStore(db_path, principal=principal).create_packet(
        agent_id="worker.frontend",
        task_id=first.task_id,
        run_id=run.run_id,
        summary="Frontend assignment context",
        actor="controller",
    )
    ContextStore(db_path, principal=principal).create_packet(
        agent_id="worker.backend",
        task_id=second.task_id,
        run_id=run.run_id,
        summary="Backend assignment context",
        actor="controller",
    )
    GateBoard(db_path=db_path, principal=principal).create_gate(
        "Frontend QA",
        run_id=run.run_id,
        task_id=first.task_id,
        requested_by="worker.frontend",
    )
    EventStore(db_path).append_event(
        BusEvent(
            type=EventType.TASK_PROGRESS_REPORTED,
            actor="worker.backend",
            run_id=run.run_id,
            task_id=second.task_id,
            payload={"task_id": second.task_id, "summary": "Backend progress"},
        )
    )

    ui = build_operations_projection(db_path).ui

    assert set(ui.task_workflows) == {first.task_id, second.task_id}
    assert ui.selected_task_workflow.task_ids in ([first.task_id], [second.task_id])
    assert ui.task_workflow.task_ids == [first.task_id, second.task_id]
    assert ui.metro.task_ids == [first.task_id, second.task_id]

    for task_id, workflow in ui.task_workflows.items():
        assert workflow.task_ids == [task_id]
        assert all(node.task_id in (None, task_id) for node in workflow.nodes)
        assert all(edge.task_id in (None, "", task_id) for edge in workflow.edges)
        assert not any(
            edge.source == f"task:{first.task_id}" and edge.target == f"task:{second.task_id}"
            for edge in workflow.edges
        )
        assert not any(
            edge.source == f"task:{second.task_id}" and edge.target == f"task:{first.task_id}"
            for edge in workflow.edges
        )


def test_task_workflow_clusters_replacement_events(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    principal = controller_principal()
    tasks = TaskBoard(db_path=db_path, principal=principal)
    run = tasks.create_run("Wave9", objective="Cluster workflow facts", created_by="controller")
    task = tasks.create_task("Replacement-heavy task", run_id=run.run_id, owner_agent_id="controller")
    store = EventStore(db_path)

    for index in range(5):
        store.append_event(
            BusEvent(
                type=EventType.REPLACEMENT_RECOMMENDED,
                actor="runtime-helper-2",
                run_id=run.run_id,
                task_id=task.task_id,
                payload={
                    "recommendation_id": f"rec-{index}",
                    "summary": f"replacement candidate {index}",
                    "task_id": task.task_id,
                },
            )
        )

    workflow = build_operations_projection(db_path).ui.selected_task_workflow
    replacement_nodes = [node for node in workflow.nodes if node.kind == "replacement"]
    cluster_nodes = [node for node in workflow.nodes if node.kind == "cluster:replacement"]

    assert replacement_nodes == []
    assert len(cluster_nodes) == 1
    assert "Replacement" in cluster_nodes[0].title
    assert cluster_nodes[0].state == "recommended"
