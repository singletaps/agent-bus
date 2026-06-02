from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from agent_bus.agents import AgentDirectory
from agent_bus.authority import agent_principal, controller_principal
from agent_bus.fencing import FencingService
from agent_bus.gates import GateBoard
from agent_bus.inbox import InboxStore
from agent_bus.models import AgentRuntimeState, CapabilityEvidenceSource, EventType, TaskState
from agent_bus.projections import build_operations_projection
from agent_bus.protocol_models import ClaimStatus, TaskClaimKind
from agent_bus.server import create_app
from agent_bus.tasks import TaskBoard


def _wait_and_ack(client: TestClient, agent_id: str) -> dict:
    delivered = client.post(
        "/api/inbox/wait",
        json={"agent_id": agent_id, "timeout": 0.01, "poll_interval": 0.005},
    )
    assert delivered.status_code == 200
    item = delivered.json()["item"]
    assert item is not None

    acked = client.post("/api/inbox/ack", json={"agent_id": agent_id, "inbox_id": item["inbox_id"]})
    assert acked.status_code == 200
    assert acked.json()["acked"] is True
    return item


def _latest_claim(
    db_path,
    *,
    task_id: str,
    agent_id: str,
    claim_kind: TaskClaimKind,
) -> sqlite3.Row:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        claim = conn.execute(
            """
            select * from task_claims
            where task_id = ? and agent_id = ? and claim_kind = ?
            order by created_at desc
            limit 1
            """,
            (task_id, agent_id, claim_kind.value),
        ).fetchone()
    assert claim is not None
    return claim


def _commit_claim(client: TestClient, claim_id: str, *, expected_status: str) -> dict:
    response = client.post(f"/api/controller/task-claims/{claim_id}/commit", json={"actor": "controller"})
    assert response.status_code == 200
    body = response.json()
    assert body["claim"]["status"] == ClaimStatus.COMMITTED.value
    assert body["task"]["status"] == expected_status
    return body


def _event_types(db_path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        return [row[0] for row in conn.execute("select type from event_log order by seq asc")]


def test_live_four_agent_protocol_simulation_covers_claims_gate_interrupt_and_replacement(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("worker.frontend", role="worker", declared_capabilities=["react"])
    directory.register_identity("worker.backend", role="worker", declared_capabilities=["python", "react"])
    directory.register_identity("runtime-qa", role="qa", declared_capabilities=["browser-qa", "protocol-qa"])
    frontend_session = directory.start_session(
        "worker.frontend",
        run_id="run-wave6-live",
        session_id="session-frontend",
        runtime_state=AgentRuntimeState.STANDBY_READY,
    )
    backend_session = directory.start_session(
        "worker.backend",
        run_id="run-wave6-live",
        session_id="session-backend",
        runtime_state=AgentRuntimeState.STANDBY_READY,
    )
    qa_session = directory.start_session(
        "runtime-qa",
        run_id="run-wave6-live",
        session_id="session-qa",
        runtime_state=AgentRuntimeState.STANDBY_READY,
    )
    directory.record_capability_evidence(
        "worker.backend",
        "react",
        CapabilityEvidenceSource.QA_CONFIRMED,
        confidence=0.98,
    )
    directory.record_capability_evidence(
        "worker.backend",
        "python",
        CapabilityEvidenceSource.USER_ASSIGNED,
        confidence=0.95,
    )
    frontend_fence = FencingService(db_path).register_session(
        frontend_session.session_id,
        agent_id="worker.frontend",
        token="frontend-token",
    )
    backend_fence = FencingService(db_path).register_session(
        backend_session.session_id,
        agent_id="worker.backend",
        token="backend-token",
    )
    FencingService(db_path).register_session(
        qa_session.session_id,
        agent_id="runtime-qa",
        token="qa-token",
    )

    board = TaskBoard(db_path=db_path, agent_directory=directory, principal=controller)
    run = board.create_run(
        "Wave6 live protocol simulation",
        objective="Exercise controller, workers, QA, gates, interrupts, and replacement.",
        created_by="controller",
        run_id="run-wave6-live",
    )
    frontend_task = board.create_task(
        "Frontend convergence slice",
        run_id=run.run_id,
        owner_agent_id="controller",
    )
    backend_task = board.create_task(
        "Backend protocol adapter slice",
        run_id=run.run_id,
        owner_agent_id="controller",
    )
    frontend_task = board.assign_task(frontend_task.task_id, "worker.frontend", actor="controller")
    backend_task = board.assign_task(backend_task.task_id, "worker.backend", actor="controller")
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    frontend_assignment = _wait_and_ack(client, "worker.frontend")
    backend_assignment = _wait_and_ack(client, "worker.backend")
    assert frontend_assignment["kind"] == "task_assigned"
    assert frontend_assignment["payload"]["task_id"] == frontend_task.task_id
    assert backend_assignment["kind"] == "task_assigned"
    assert backend_assignment["payload"]["task_id"] == backend_task.task_id

    board.acknowledge_task(
        frontend_task.task_id,
        actor="worker.frontend",
        principal=agent_principal("worker.frontend", session_id=frontend_fence.session_id),
        session_id=frontend_fence.session_id,
        session_epoch=frontend_fence.session_epoch,
        fencing_token=frontend_fence.raw_token,
    )
    frontend_ack_claim = _latest_claim(
        db_path,
        task_id=frontend_task.task_id,
        agent_id="worker.frontend",
        claim_kind=TaskClaimKind.ACK,
    )
    assert frontend_ack_claim["status"] == ClaimStatus.PENDING.value
    _commit_claim(client, frontend_ack_claim["claim_id"], expected_status=TaskState.ACKNOWLEDGED.value)

    board.start_task(
        frontend_task.task_id,
        actor="worker.frontend",
        principal=agent_principal("worker.frontend", session_id=frontend_fence.session_id),
        session_id=frontend_fence.session_id,
        session_epoch=frontend_fence.session_epoch,
        fencing_token=frontend_fence.raw_token,
    )
    frontend_progress_claim = _latest_claim(
        db_path,
        task_id=frontend_task.task_id,
        agent_id="worker.frontend",
        claim_kind=TaskClaimKind.PROGRESS,
    )
    _commit_claim(client, frontend_progress_claim["claim_id"], expected_status=TaskState.WORKING.value)

    board.acknowledge_task(
        backend_task.task_id,
        actor="worker.backend",
        principal=agent_principal("worker.backend", session_id=backend_fence.session_id),
        session_id=backend_fence.session_id,
        session_epoch=backend_fence.session_epoch,
        fencing_token=backend_fence.raw_token,
    )
    backend_ack_claim = _latest_claim(
        db_path,
        task_id=backend_task.task_id,
        agent_id="worker.backend",
        claim_kind=TaskClaimKind.ACK,
    )
    _commit_claim(client, backend_ack_claim["claim_id"], expected_status=TaskState.ACKNOWLEDGED.value)

    board.start_task(
        backend_task.task_id,
        actor="worker.backend",
        principal=agent_principal("worker.backend", session_id=backend_fence.session_id),
        session_id=backend_fence.session_id,
        session_epoch=backend_fence.session_epoch,
        fencing_token=backend_fence.raw_token,
    )
    backend_progress_claim = _latest_claim(
        db_path,
        task_id=backend_task.task_id,
        agent_id="worker.backend",
        claim_kind=TaskClaimKind.PROGRESS,
    )
    _commit_claim(client, backend_progress_claim["claim_id"], expected_status=TaskState.WORKING.value)

    qa_artifact = board.create_artifact(
        "qa-report",
        "artifact://wave6/runtime-qa-browser-and-protocol",
        run_id=run.run_id,
        task_id=frontend_task.task_id,
        created_by="runtime-qa",
        metadata={"summary": "runtime QA accepted frontend evidence"},
    )
    gate = GateBoard(db_path=db_path, principal=controller).create_gate(
        "Runtime QA approval",
        run_id=run.run_id,
        task_id=frontend_task.task_id,
        owner_agent_id="runtime-qa",
        requested_by="runtime-qa",
        checklist=["simulation covers claim commit", "simulation covers gate approval"],
        required_evidence=[qa_artifact.artifact_id],
    )
    approved_gate = client.post(
        f"/api/controller/gates/{gate.gate_id}/approve",
        json={"actor": "controller", "evidence_artifact_ids": [qa_artifact.artifact_id]},
    )
    assert approved_gate.status_code == 200
    assert approved_gate.json()["gate"]["state"] == "approved"
    assert approved_gate.json()["gate"]["decision_actor"] == "controller"

    interrupt = client.post(
        "/api/user/interrupts",
        json={
            "actor": "user",
            "text": "Pause backend until QA has checked the frontend handoff.",
            "run_id": run.run_id,
            "task_id": backend_task.task_id,
            "target": {
                "controller": "controller",
                "observer": None,
                "task_owner": "controller",
                "task_assignee": "worker.backend",
                "qa_agent": "runtime-qa",
            },
        },
    )
    assert interrupt.status_code == 200
    interrupt_body = interrupt.json()
    assert {"controller", "worker.backend", "runtime-qa"} <= set(interrupt_body["affected_agents"])
    assert interrupt_body["invalidated_packet_ids_by_agent"]["worker.backend"]

    directory.report_context_loss(frontend_session.session_id, reason="frontend runtime context lost")
    recommendations = client.get(
        "/api/replacement/recommendations",
        params=[
            ("session_id", frontend_session.session_id),
            ("task_id", frontend_task.task_id),
            ("run_id", run.run_id),
            ("required_capability", "react"),
            ("role", "worker"),
        ],
    )
    assert recommendations.status_code == 200
    backend_recommendation = next(
        item
        for item in recommendations.json()["recommendations"]
        if item["candidate"]["agent_id"] == "worker.backend"
    )
    replacement = client.post(
        "/api/replacement/approve",
        json={
            "recommendation_id": backend_recommendation["recommendation_id"],
            "task_id": frontend_task.task_id,
            "old_session_id": frontend_session.session_id,
            "old_agent_id": "worker.frontend",
            "candidate_agent_id": "worker.backend",
            "candidate_session_id": backend_session.session_id,
            "run_id": run.run_id,
            "trigger_names": [trigger["name"] for trigger in backend_recommendation["triggers"]],
            "required_capabilities": ["react"],
            "role": "worker",
            "approved_by": "controller",
            "next_action": "worker.backend assumes the frontend role from the rehydration packet",
            "required_artifacts": [qa_artifact.artifact_id],
        },
    )
    assert replacement.status_code == 200
    replacement_body = replacement.json()
    assert replacement_body["context_packet"]["agent_id"] == "worker.backend"
    assert replacement_body["context_packet"]["instructions"]["kind"] == "rehydration"
    assert replacement_body["context_packet"]["instructions"]["role_contract"] == "replacement for worker.frontend"
    assert replacement_body["event_chain"][2]["payload"]["old_agent_id"] == "worker.frontend"

    reloaded_directory = AgentDirectory(db_path=db_path)
    old_frontend = reloaded_directory.get_session(frontend_session.session_id)
    backend_after_transfer = reloaded_directory.get_session(backend_session.session_id)
    reassigned_frontend_task = TaskBoard(db_path=db_path).get_task(frontend_task.task_id)
    assert old_frontend.runtime_state is AgentRuntimeState.REPLACED
    assert old_frontend.replaced_by_session_id == backend_session.session_id
    assert backend_after_transfer.runtime_state is AgentRuntimeState.REHYDRATING
    assert reassigned_frontend_task.status is TaskState.REASSIGNED
    assert reassigned_frontend_task.assignee_agent_id == "worker.backend"

    with pytest.raises(PermissionError):
        board.start_task(
            frontend_task.task_id,
            actor="worker.frontend",
            principal=agent_principal("worker.frontend", session_id=frontend_fence.session_id),
            session_id=frontend_fence.session_id,
            session_epoch=frontend_fence.session_epoch,
            fencing_token=frontend_fence.raw_token,
        )

    backend_inbox_kinds = {item.kind for item in InboxStore(db_path).list_items("worker.backend")}
    assert {"user_interrupt", "replacement_notice"} <= backend_inbox_kinds

    event_types = _event_types(db_path)
    assert {
        EventType.RUN_CREATED.value,
        EventType.TASK_CREATED.value,
        EventType.TASK_ASSIGNED.value,
        EventType.TASK_ACK_CLAIMED.value,
        EventType.TASK_ACKNOWLEDGED.value,
        EventType.TASK_PROGRESS_REPORTED.value,
        EventType.TASK_PROGRESS.value,
        EventType.ARTIFACT_CREATED.value,
        EventType.GATE_OPENED.value,
        EventType.GATE_APPROVED.value,
        EventType.USER_INTERRUPT_CREATED.value,
        EventType.REPLACEMENT_RECOMMENDED.value,
        EventType.REPLACEMENT_APPROVAL_REQUESTED.value,
        EventType.REPLACEMENT_APPROVED.value,
        EventType.REPLACEMENT_REASSIGNMENT_COMMITTED.value,
        EventType.TASK_REASSIGNED.value,
    } <= set(event_types)

    with sqlite3.connect(db_path) as conn:
        missing_protocol_effects = conn.execute(
            """
            select type from event_log
            where type in (
                'task.ack_claimed',
                'task.acknowledged',
                'task.progress_reported',
                'task.progress',
                'replacement.approved',
                'replacement.reassignment_committed',
                'task.reassigned'
            )
              and (projection_effect is null or fencing_result is null)
            """
        ).fetchall()
        committed_claim_count = conn.execute(
            "select count(*) from task_claims where status = ?",
            (ClaimStatus.COMMITTED.value,),
        ).fetchone()[0]
    assert missing_protocol_effects == []
    assert committed_claim_count == 4

    projection = build_operations_projection(db_path)
    workflow = projection.ui.task_workflow
    workflow_kinds = {node.kind for node in workflow.nodes}
    assert {frontend_task.task_id, backend_task.task_id} <= set(workflow.task_ids)
    assert {"task", "context", "claim", "gate", "artifact", "replacement"} <= workflow_kinds
    assert not workflow.diagnostics
