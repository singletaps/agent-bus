from __future__ import annotations

import json
import sqlite3

import pytest

from agent_bus.authority import agent_principal, controller_principal
from agent_bus.fencing import FencingService
from agent_bus.models import TaskState
from agent_bus.protocol_models import ClaimStatus, FencingResult, ProjectionEffect
from agent_bus.tasks import TaskBoard


def test_fenced_worker_ack_creates_claim_without_task_state_commit(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    board = TaskBoard(db_path=db_path, principal=controller)
    task = board.create_task("Claimable task", owner_agent_id="controller")
    assigned = board.assign_task(task.task_id, "worker.backend", actor="controller")
    fence = FencingService(db_path).register_session(
        "session-worker",
        agent_id="worker.backend",
        token="worker-token",
    )

    returned = board.acknowledge_task(
        assigned.task_id,
        actor="worker.backend",
        principal=agent_principal("worker.backend", session_id=fence.session_id),
        session_id=fence.session_id,
        session_epoch=fence.session_epoch,
        fencing_token=fence.raw_token,
    )

    assert returned.status is TaskState.ASSIGNED
    assert board.get_task(assigned.task_id).status is TaskState.ASSIGNED
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        claim = conn.execute("select * from task_claims").fetchone()
        event = conn.execute("select * from event_log where type = 'task.ack_claimed'").fetchone()
        effect = conn.execute("select * from projection_effects where event_id = ?", (event["event_id"],)).fetchone()

    assert claim["claim_kind"] == "ack"
    assert claim["status"] == ClaimStatus.PENDING.value
    assert claim["task_id"] == assigned.task_id
    assert claim["agent_id"] == "worker.backend"
    assert claim["session_id"] == fence.session_id
    assert claim["context_packet_id"] is not None
    assert event["projection_effect"] == ProjectionEffect.COMMIT.value
    assert event["fencing_result"] == FencingResult.VALID.value
    assert effect["target_table"] == "task_claims"
    assert effect["target_id"] == claim["claim_id"]


def test_controller_commit_claim_moves_task_and_links_claim_to_decision(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    board = TaskBoard(db_path=db_path, principal=controller)
    task = board.create_task("Commit claim", owner_agent_id="controller")
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

    committed = board.commit_task_claim(claim_id, actor="controller", principal=controller)

    assert committed.status is TaskState.ACKNOWLEDGED
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        claim = conn.execute("select * from task_claims where claim_id = ?", (claim_id,)).fetchone()
        event = conn.execute("select * from event_log where event_id = ?", (claim["committed_by_event_id"],)).fetchone()

    assert claim["status"] == ClaimStatus.COMMITTED.value
    assert event["type"] == "task.acknowledged"
    assert event["projection_effect"] == ProjectionEffect.COMMIT.value


def test_worker_cannot_commit_own_claim(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    board = TaskBoard(db_path=db_path, principal=controller)
    task = board.create_task("Reject self commit", owner_agent_id="controller")
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

    with pytest.raises(PermissionError):
        board.commit_task_claim(
            claim_id,
            actor="worker.backend",
            principal=agent_principal("worker.backend", session_id=fence.session_id),
            session_id=fence.session_id,
            session_epoch=fence.session_epoch,
            fencing_token=fence.raw_token,
        )

    assert board.get_task(assigned.task_id).status is TaskState.ASSIGNED


def test_controller_reject_claim_records_rejected_status_without_task_mutation(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    board = TaskBoard(db_path=db_path, principal=controller)
    task = board.create_task("Reject claim", owner_agent_id="controller")
    assigned = board.assign_task(task.task_id, "worker.backend", actor="controller")
    fence = FencingService(db_path).register_session(
        "session-worker",
        agent_id="worker.backend",
        token="worker-token",
    )
    board.block_task(
        assigned.task_id,
        "blocked on user input",
        actor="worker.backend",
        principal=agent_principal("worker.backend", session_id=fence.session_id),
        session_id=fence.session_id,
        session_epoch=fence.session_epoch,
        fencing_token=fence.raw_token,
    )
    with sqlite3.connect(db_path) as conn:
        claim_id = conn.execute("select claim_id from task_claims").fetchone()[0]

    board.reject_task_claim(claim_id, reason="needs clearer blocker", actor="controller", principal=controller)

    assert board.get_task(assigned.task_id).status is TaskState.ASSIGNED
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        claim = conn.execute("select status, payload_json from task_claims where claim_id = ?", (claim_id,)).fetchone()
    assert claim["status"] == ClaimStatus.REJECTED.value
    assert json.loads(claim["payload_json"])["rejection_reason"] == "needs clearer blocker"
