from __future__ import annotations

import json
import sqlite3

import pytest

from agent_bus.authority import agent_principal, controller_principal
from agent_bus.fencing import FencingService
from agent_bus.protocol_models import ClaimStatus
from agent_bus.tasks import TaskBoard


def test_fenced_worker_artifact_production_is_claim_not_artifact_commit(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    board = TaskBoard(db_path=db_path, principal=controller)
    task = board.create_task("Produce artifact", run_id="run-1", owner_agent_id="controller")
    assigned = board.assign_task(task.task_id, "worker.backend", actor="controller")
    fence = FencingService(db_path).register_session(
        "session-worker",
        agent_id="worker.backend",
        token="worker-token",
    )

    result = board.produce_artifact_claim(
        "test-log",
        "coordination/output.txt",
        task_id=assigned.task_id,
        run_id="run-1",
        metadata={"passed": 3},
        actor="worker.backend",
        principal=agent_principal("worker.backend", session_id=fence.session_id),
        session_id=fence.session_id,
        session_epoch=fence.session_epoch,
        fencing_token=fence.raw_token,
    )

    assert result.accepted is True
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        artifact_count = conn.execute("select count(*) from artifacts").fetchone()[0]
        claim = conn.execute("select * from task_claims").fetchone()
        event = conn.execute("select * from event_log where type = 'artifact.produced'").fetchone()

    assert artifact_count == 0
    assert claim["claim_kind"] == "artifact"
    assert claim["status"] == ClaimStatus.PENDING.value
    assert json.loads(claim["payload_json"])["artifact"]["uri"] == "coordination/output.txt"
    assert event["artifact_id"] is not None


def test_controller_accepting_artifact_claim_creates_authoritative_artifact(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    board = TaskBoard(db_path=db_path, principal=controller)
    task = board.create_task("Accept artifact", run_id="run-1", owner_agent_id="controller")
    assigned = board.assign_task(task.task_id, "worker.backend", actor="controller")
    fence = FencingService(db_path).register_session(
        "session-worker",
        agent_id="worker.backend",
        token="worker-token",
    )
    claim_result = board.produce_artifact_claim(
        "test-log",
        "coordination/output.txt",
        task_id=assigned.task_id,
        run_id="run-1",
        metadata={"passed": 3},
        actor="worker.backend",
        principal=agent_principal("worker.backend", session_id=fence.session_id),
        session_id=fence.session_id,
        session_epoch=fence.session_epoch,
        fencing_token=fence.raw_token,
    )

    artifact = board.commit_artifact_claim(claim_result.claim_id, actor="controller", principal=controller)

    assert artifact.task_id == assigned.task_id
    assert artifact.created_by == "worker.backend"
    assert artifact.claim_id == claim_result.claim_id
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        claim = conn.execute("select status, committed_by_event_id from task_claims").fetchone()
        row = conn.execute("select * from artifacts where artifact_id = ?", (artifact.artifact_id,)).fetchone()
        event = conn.execute("select * from event_log where event_id = ?", (claim["committed_by_event_id"],)).fetchone()

    assert claim["status"] == ClaimStatus.COMMITTED.value
    assert row["claim_id"] == claim_result.claim_id
    assert event["type"] == "artifact.created"


def test_worker_cannot_create_authoritative_artifact_directly(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    board = TaskBoard(db_path=db_path)
    fence = FencingService(db_path).register_session(
        "session-worker",
        agent_id="worker.backend",
        token="worker-token",
    )

    with pytest.raises(PermissionError):
        board.create_artifact(
            "test-log",
            "coordination/output.txt",
            task_id="task-1",
            created_by="worker.backend",
            principal=agent_principal("worker.backend", session_id=fence.session_id),
            session_id=fence.session_id,
            session_epoch=fence.session_epoch,
            fencing_token=fence.raw_token,
        )
