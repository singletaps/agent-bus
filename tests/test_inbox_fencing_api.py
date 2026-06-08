from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from agent_bus.authority import controller_principal
from agent_bus.fencing import FencingService
from agent_bus.inbox import InboxStore
from agent_bus.server import create_app


def _queued_item(db_path):
    store = InboxStore(db_path, principal=controller_principal())
    try:
        return store.enqueue("worker.backend", "task_assigned", {"task_id": "task-1"}, actor="controller")
    finally:
        store.close()


def _status(db_path, inbox_id: str) -> str:
    with sqlite3.connect(db_path) as conn:
        return str(conn.execute("select status from inbox_items where inbox_id = ?", (inbox_id,)).fetchone()[0])


def test_legacy_inbox_wait_without_fence_is_deprecated_and_does_not_deliver(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    item = _queued_item(db_path)
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    response = client.post(
        "/api/inbox/wait",
        json={"agent_id": "worker.backend", "timeout": 0.01, "poll_interval": 0.005},
    )

    assert response.status_code in {400, 403, 409}
    assert _status(db_path, item.inbox_id) == "queued"
    with sqlite3.connect(db_path) as conn:
        audit = conn.execute(
            "select projection_effect from event_log where type = 'adapter.deprecated_path_used'"
        ).fetchone()
    assert audit == ("AUDIT_ONLY",)


def test_worker_inbox_wait_and_ack_require_valid_fence(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    item = _queued_item(db_path)
    fence = FencingService(db_path).register_session(
        "session-worker",
        agent_id="worker.backend",
        token="worker-token",
    )
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    missing = client.post(
        "/api/worker/inbox/wait",
        json={"agent_id": "worker.backend", "timeout": 0.01, "poll_interval": 0.005},
    )
    assert missing.status_code in {400, 403, 409, 422}
    assert _status(db_path, item.inbox_id) == "queued"

    delivered = client.post(
        "/api/worker/inbox/wait",
        json={
            "agent_id": "worker.backend",
            "session_id": fence.session_id,
            "session_epoch": fence.session_epoch,
            "fencing_token": fence.raw_token,
            "timeout": 0.01,
            "poll_interval": 0.005,
        },
    )
    assert delivered.status_code == 200
    delivered_body = delivered.json()
    assert delivered_body["item"]["inbox_id"] == item.inbox_id
    assert delivered_body["item"]["delivered_to_session_id"] == fence.session_id

    legacy_ack = client.post("/api/inbox/ack", json={"agent_id": "worker.backend", "inbox_id": item.inbox_id})
    assert legacy_ack.status_code in {400, 403, 409}
    assert _status(db_path, item.inbox_id) == "delivered"

    acked = client.post(
        "/api/worker/inbox/ack",
        json={
            "agent_id": "worker.backend",
            "inbox_id": item.inbox_id,
            "session_id": fence.session_id,
            "session_epoch": fence.session_epoch,
            "fencing_token": fence.raw_token,
        },
    )
    assert acked.status_code == 200
    assert acked.json()["acked"] is True
    assert _status(db_path, item.inbox_id) == "acked"
