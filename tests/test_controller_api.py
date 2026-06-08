from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from agent_bus.authority import agent_principal, controller_principal, user_principal
from agent_bus.context import ContextStore
from agent_bus.fencing import FencingService
from agent_bus.gates import GateBoard
from agent_bus.models import TaskState
from agent_bus.protocol_models import ClaimStatus, ProjectionEffect
from agent_bus.server import create_app
from agent_bus.tasks import TaskBoard


def test_controller_gate_api_canonical_route_approves_and_legacy_route_audits(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    board = TaskBoard(db_path=db_path, principal=controller)
    run = board.create_run("Controller routes", objective="split API", created_by="controller")
    task = board.create_task(
        "Approve gate",
        run_id=run.run_id,
        owner_agent_id="controller",
        assignee_agent_id="worker.backend",
    )
    evidence = board.create_artifact(
        "test-log",
        "file://pytest.log",
        run_id=run.run_id,
        task_id=task.task_id,
        created_by="worker.backend",
    )
    gates = GateBoard(db_path=db_path, principal=controller)
    canonical_gate = gates.create_gate(
        "Canonical gate",
        run_id=run.run_id,
        task_id=task.task_id,
        requested_by="worker.backend",
        required_evidence=[evidence.artifact_id],
    )
    legacy_gate = gates.create_gate(
        "Legacy gate",
        run_id=run.run_id,
        task_id=task.task_id,
        requested_by="worker.backend",
        required_evidence=[evidence.artifact_id],
    )
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    canonical = client.post(
        f"/api/controller/gates/{canonical_gate.gate_id}/approve",
        json={"evidence_artifact_ids": [evidence.artifact_id]},
    )
    legacy = client.post(
        f"/api/gates/{legacy_gate.gate_id}/approve",
        json={"actor": "controller", "evidence_artifact_ids": [evidence.artifact_id]},
    )

    assert canonical.status_code == 200
    assert canonical.json()["gate"]["decision_actor"] == "controller"
    assert legacy.status_code == 200

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        audit = conn.execute(
            "select * from event_log where type = 'adapter.deprecated_path_used'"
        ).fetchone()

    assert audit is not None
    assert audit["projection_effect"] == ProjectionEffect.AUDIT_ONLY.value
    assert "api.gates.approve" in audit["payload_json"]
    assert "api.controller.gates.approve" in audit["payload_json"]


def test_controller_claim_api_commits_worker_claim(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    board = TaskBoard(db_path=db_path, principal=controller)
    task = board.create_task("Commit worker claim", owner_agent_id="controller")
    assigned = board.assign_task(task.task_id, "worker.backend", actor="controller")
    fence = FencingService(db_path).register_session(
        "session-worker",
        agent_id="worker.backend",
        token="worker-token",
    )
    board.acknowledge_task(
        assigned.task_id,
        actor="worker.backend",
        principal=agent_principal("worker.backend", session_id=fence.session_id),
        session_id=fence.session_id,
        session_epoch=fence.session_epoch,
        fencing_token=fence.raw_token,
    )
    with sqlite3.connect(db_path) as conn:
        claim_id = conn.execute("select claim_id from task_claims").fetchone()[0]
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    response = client.post(f"/api/controller/task-claims/{claim_id}/commit", json={"actor": "controller"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["claim"]["claim_id"] == claim_id
    assert body["claim"]["status"] == ClaimStatus.COMMITTED.value
    assert body["task"]["status"] == TaskState.ACKNOWLEDGED.value


def test_user_interrupt_api_canonical_route_and_legacy_route_audit(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    context = ContextStore(db_path, principal=user_principal())
    affected = context.create_packet(
        agent_id="worker.owner",
        task_id="task-1",
        run_id="run-1",
        summary="affected",
        actor="user",
    )
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    canonical = client.post(
        "/api/user/interrupts",
        json={
            "actor": "user",
            "text": "pause and replan",
            "run_id": "run-1",
            "task_id": "task-1",
            "target": {"task_owner": "worker.owner"},
        },
    )
    legacy = client.post(
        "/api/interrupt",
        json={
            "actor": "user",
            "text": "legacy pause",
            "run_id": "run-1",
            "task_id": "task-1",
            "target": {"additional_agents": ["worker.extra"]},
        },
    )

    assert canonical.status_code == 200
    assert canonical.json()["invalidated_packet_ids_by_agent"]["worker.owner"] == [affected.packet_id]
    assert legacy.status_code == 200

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        audit = conn.execute(
            """
            select * from event_log
            where type = 'adapter.deprecated_path_used'
              and payload_json like '%api.interrupt%'
            """
        ).fetchone()

    assert audit is not None
    assert audit["projection_effect"] == ProjectionEffect.AUDIT_ONLY.value
