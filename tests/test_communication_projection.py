from __future__ import annotations

from fastapi.testclient import TestClient

from agent_bus.fencing import FencingService
from agent_bus.inbox import InboxStore
from agent_bus.server import create_app


def test_operator_message_projects_delivery_and_ack_state(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    sent = client.post(
        "/api/messages/send",
        json={
            "actor": "operator",
            "text": "Please inspect the failed task.",
            "recipient_agent_ids": ["worker.one"],
            "run_id": "run-1",
            "task_id": "task-1",
            "message_type": "instruction",
            "priority": "high",
        },
    ).json()
    messages = client.get("/api/projections/messages").json()["messages"]

    assert sent["ok"] is True
    assert sent["affected_agents"] == ["worker.one"]
    assert messages[0]["body"] == "Please inspect the failed task."
    assert messages[0]["recipient_agent_ids"] == ["worker.one"]
    assert messages[0]["delivery_state"] == "sent"
    assert messages[0]["ack_state"] == "waiting_ack"
    assert messages[0]["priority"] == "high"
    assert messages[0]["links"]["run_id"] == "run-1"
    assert messages[0]["links"]["task_ids"] == ["task-1"]


def test_operator_message_delivery_state_tracks_inbox_delivery(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    client.post(
        "/api/messages/send",
        json={
            "actor": "operator",
            "text": "Please acknowledge receipt.",
            "recipient_agent_ids": ["worker.one"],
            "message_type": "instruction",
        },
    )
    before_delivery = client.get("/api/projections/messages").json()["messages"][0]
    fence = FencingService(db_path).register_session(
        "session-worker-one",
        agent_id="worker.one",
        token="worker-token",
    )

    delivered = client.post(
        "/api/worker/inbox/wait",
        json={
            "agent_id": "worker.one",
            "session_id": fence.session_id,
            "session_epoch": fence.session_epoch,
            "fencing_token": fence.raw_token,
            "timeout": 0.01,
            "poll_interval": 0.005,
        },
    ).json()
    after_delivery = client.get("/api/projections/messages").json()["messages"][0]

    assert delivered["ok"] is True
    assert delivered["noop"] is False
    assert before_delivery["delivery_state"] == "sent"
    assert after_delivery["delivery_state"] == "delivered"
    assert after_delivery["ack_state"] == "waiting_ack"


def test_operator_message_ack_state_uses_interrupt_event_inbox_links(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))
    client.post(
        "/api/messages/send",
        json={
            "actor": "operator",
            "text": "Proceed after QA approval.",
            "recipient_agent_ids": ["worker.one"],
            "gate_id": "gate-1",
        },
    )
    store = InboxStore(db_path)
    try:
        for item in store.list_items("worker.one"):
            store.ack(item.inbox_id, agent_id="worker.one")
    finally:
        store.close()

    message = client.get("/api/projections/messages").json()["messages"][0]

    assert message["ack_state"] == "acked"
    assert message["links"]["gate_ids"] == ["gate-1"]


def test_operator_question_message_projects_waiting_reply(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    client.post(
        "/api/messages/send",
        json={
            "actor": "operator",
            "text": "Can you confirm the gate evidence?",
            "recipient_agent_ids": ["worker.one"],
            "message_type": "question",
        },
    )

    message = client.get("/api/projections/messages").json()["messages"][0]

    assert message["message_type"] == "question"
    assert message["reply_state"] == "waiting_reply"
