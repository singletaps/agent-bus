from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from agent_bus.authority import controller_principal
from agent_bus.fencing import FencingService
from agent_bus.models import TaskState
from agent_bus.protocol_models import ClaimStatus, FencingResult, ProjectionEffect
from agent_bus.server import create_app
from agent_bus.tasks import TaskBoard


def _assigned_task_with_context(db_path):
    board = TaskBoard(db_path=db_path, principal=controller_principal())
    task = board.create_task("Fenced completion claim", owner_agent_id="controller")
    assigned = board.assign_task(task.task_id, "worker.backend", actor="controller")
    fence = FencingService(db_path).register_session(
        "session-worker",
        agent_id="worker.backend",
        token="worker-token",
    )
    with sqlite3.connect(db_path) as conn:
        context_packet_id = conn.execute(
            """
            select context_packet_id
              from task_context_bindings
             where task_id = ?
               and agent_id = ?
               and status = 'active'
             order by created_at desc
             limit 1
            """,
            (assigned.task_id, "worker.backend"),
        ).fetchone()[0]
    return assigned, fence, context_packet_id


def test_worker_completion_claim_route_requires_fenced_payload(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    assigned, fence, context_packet_id = _assigned_task_with_context(db_path)
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    response = client.post(
        f"/api/worker/tasks/{assigned.task_id}/completion-claim",
        json={
            "actor": "worker.backend",
            "session_id": fence.session_id,
            "session_epoch": fence.session_epoch,
            "context_packet_id": context_packet_id,
            "payload": {"summary": "ready for controller commit"},
        },
    )

    assert response.status_code == 422
    with sqlite3.connect(db_path) as conn:
        claim_count = conn.execute("select count(*) from task_claims").fetchone()[0]
    assert claim_count == 0


def test_worker_completion_claim_api_creates_pending_fenced_claim(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    assigned, fence, context_packet_id = _assigned_task_with_context(db_path)
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    response = client.post(
        f"/api/worker/tasks/{assigned.task_id}/completion-claim",
        json={
            "actor": "worker.backend",
            "session_id": fence.session_id,
            "session_epoch": fence.session_epoch,
            "fencing_token": fence.raw_token,
            "context_packet_id": context_packet_id,
            "payload": {"summary": "ready for controller commit"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["claim"]["task_id"] == assigned.task_id
    assert body["claim"]["claim_kind"] == "completion"
    assert body["claim"]["status"] == ClaimStatus.PENDING.value
    assert body["claim"]["context_packet_id"] == context_packet_id
    assert body["projection_effect"] == ProjectionEffect.COMMIT.value
    assert body["fencing_result"] == FencingResult.VALID.value
    assert body["task"]["status"] == TaskState.ASSIGNED.value
    assert TaskBoard(db_path=db_path).get_task(assigned.task_id).status is TaskState.ASSIGNED

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        event = conn.execute(
            "select * from event_log where type = 'task.completion_claimed'"
        ).fetchone()
        effect = conn.execute(
            "select * from projection_effects where event_id = ?",
            (event["event_id"],),
        ).fetchone()

    assert event["projection_effect"] == ProjectionEffect.COMMIT.value
    assert event["fencing_result"] == FencingResult.VALID.value
    assert effect["target_table"] == "task_claims"
    assert effect["target_id"] == body["claim"]["claim_id"]


def test_worker_completion_claim_api_rejects_invalid_fence_without_claim(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    assigned, fence, context_packet_id = _assigned_task_with_context(db_path)
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    response = client.post(
        f"/api/worker/tasks/{assigned.task_id}/completion-claim",
        json={
            "actor": "worker.backend",
            "session_id": fence.session_id,
            "session_epoch": fence.session_epoch,
            "fencing_token": "wrong-token",
            "context_packet_id": context_packet_id,
            "payload": {"summary": "ready for controller commit"},
        },
    )

    assert response.status_code == 403
    body = response.json()
    assert body["ok"] is False
    assert body["error"] == "fencing_reject"
    assert body["projection_effect"] == ProjectionEffect.REJECT.value
    assert body["fencing_result"] == FencingResult.INVALID.value
    with sqlite3.connect(db_path) as conn:
        claim_count = conn.execute("select count(*) from task_claims").fetchone()[0]
    assert claim_count == 0
    assert TaskBoard(db_path=db_path).get_task(assigned.task_id).status is TaskState.ASSIGNED


def test_worker_complete_route_remains_deprecated_audit_only(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    assigned, fence, context_packet_id = _assigned_task_with_context(db_path)
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    response = client.post(
        f"/api/worker/tasks/{assigned.task_id}/complete",
        json={
            "actor": "worker.backend",
            "session_id": fence.session_id,
            "session_epoch": fence.session_epoch,
            "context_packet_id": context_packet_id,
            "payload": {"summary": "legacy path"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["claim"]["status"] == ClaimStatus.NEEDS_FENCING.value
    assert body["projection_effect"] == ProjectionEffect.AUDIT_ONLY.value
    assert body["fencing_result"] == FencingResult.MISSING.value
    assert TaskBoard(db_path=db_path).get_task(assigned.task_id).status is TaskState.ASSIGNED
