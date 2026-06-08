from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from agent_bus.authority import controller_principal
from agent_bus.models import TaskState
from agent_bus.protocol_models import ClaimStatus, FencingResult, ProjectionEffect
from agent_bus.server import create_app
from agent_bus.tasks import TaskBoard


def test_worker_task_complete_api_records_audit_claim_without_task_commit(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    board = TaskBoard(db_path=db_path, principal=controller_principal())
    task = board.create_task("Worker complete API", owner_agent_id="controller")
    assigned = board.assign_task(task.task_id, "worker.backend", actor="controller")
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    response = client.post(
        f"/api/worker/tasks/{assigned.task_id}/complete",
        json={"actor": "worker.backend"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["claim"]["task_id"] == assigned.task_id
    assert body["claim"]["status"] == ClaimStatus.NEEDS_FENCING.value
    assert body["projection_effect"] == ProjectionEffect.AUDIT_ONLY.value
    assert body["fencing_result"] == FencingResult.MISSING.value
    assert body["task"]["status"] == TaskState.ASSIGNED.value
    assert TaskBoard(db_path=db_path).get_task(assigned.task_id).status is TaskState.ASSIGNED

    with sqlite3.connect(db_path) as conn:
        event = conn.execute(
            "select type, projection_effect, fencing_result from event_log where type = 'task.completion_claimed'"
        ).fetchone()
        claim = conn.execute("select status, task_id, agent_id from task_claims").fetchone()

    assert event == (
        "task.completion_claimed",
        ProjectionEffect.AUDIT_ONLY.value,
        FencingResult.MISSING.value,
    )
    assert claim == (ClaimStatus.NEEDS_FENCING.value, assigned.task_id, "worker.backend")


def test_worker_task_complete_api_rejects_control_plane_actor(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    board = TaskBoard(db_path=db_path, principal=controller_principal())
    task = board.create_task("Reject controller as worker", owner_agent_id="controller")
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    response = client.post(
        f"/api/worker/tasks/{task.task_id}/complete",
        json={"actor": "controller"},
    )

    assert response.status_code == 403
    body = response.json()
    assert body["ok"] is False
    assert body["error"] == "authority_reject"
    assert body["projection_effect"] == ProjectionEffect.REJECT.value
    assert "worker actor is required" in body["message"]
