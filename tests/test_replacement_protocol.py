from __future__ import annotations

import json
import sqlite3

import pytest

from agent_bus.agents import AgentDirectory
from agent_bus.authority import agent_principal, controller_principal
from agent_bus.context import ContextStore
from agent_bus.fencing import FencingService
from agent_bus.inbox import InboxStore
from agent_bus.models import AgentRuntimeState, CapabilityEvidenceSource, EventType, TaskState
from agent_bus.protocol_models import BindingStatus, PacketKind, SessionRole
from agent_bus.replacement import ReplacementCoordinator, ReplacementRecommendation
from agent_bus.tasks import TaskBoard


def _replacement_case(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("worker.frontend", role="worker", declared_capabilities=["react"])
    old_session = directory.start_session("worker.frontend", run_id="run-1", session_id="old-session")
    directory.register_identity("runtime-helper-2", role="worker", declared_capabilities=["react"])
    replacement_session = directory.start_session(
        "runtime-helper-2",
        run_id="run-1",
        session_id="replacement-session",
        runtime_state=AgentRuntimeState.STANDBY_READY,
    )
    directory.record_capability_evidence(
        "runtime-helper-2",
        "react",
        CapabilityEvidenceSource.USER_ASSIGNED,
        confidence=0.99,
    )
    old_fence = FencingService(db_path).register_session(
        old_session.session_id,
        agent_id=old_session.agent_id,
        token="old-token",
    )
    FencingService(db_path).register_session(
        replacement_session.session_id,
        agent_id=replacement_session.agent_id,
        token="replacement-token",
    )
    board = TaskBoard(db_path=db_path, agent_directory=directory, principal=controller)
    task = board.create_task("Continue same task", run_id="run-1", owner_agent_id="controller")
    assigned = board.assign_task(task.task_id, old_session.agent_id, actor="controller")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        old_assignment_packet_id = conn.execute(
            """
            select context_packet_id from task_context_bindings
            where task_id = ? and agent_id = ? and session_id = ? and status = ?
            """,
            (assigned.task_id, old_session.agent_id, old_session.session_id, BindingStatus.ACTIVE.value),
        ).fetchone()["context_packet_id"]

    context = ContextStore(db_path, principal=controller)
    unrelated_packet = context.create_packet(
        agent_id=old_session.agent_id,
        task_id="other-task",
        run_id="run-1",
        summary="Unrelated old session task remains active",
        actor="controller",
        session_id=old_session.session_id,
        session_epoch=old_session.session_epoch,
    )
    inbox = InboxStore(db_path, principal=controller)
    directory.report_context_loss(old_session.session_id, reason="context compression failed")
    coordinator = ReplacementCoordinator(
        directory=directory,
        inbox=inbox,
        principal=controller,
    )
    recommendation = coordinator.recommend_for_session(
        old_session.session_id,
        task_id=assigned.task_id,
        run_id="run-1",
        required_capabilities=("react",),
        role="worker",
    )
    assert isinstance(recommendation, ReplacementRecommendation)
    return {
        "db_path": db_path,
        "board": board,
        "coordinator": coordinator,
        "recommendation": recommendation,
        "task_id": assigned.task_id,
        "old_session": old_session,
        "replacement_session": replacement_session,
        "old_fence": old_fence,
        "old_assignment_packet_id": old_assignment_packet_id,
        "unrelated_packet_id": unrelated_packet.packet_id,
    }


def _replacement_events(db_path, task_id: str) -> list[sqlite3.Row]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            select * from event_log
            where task_id = ? and type like 'replacement.%'
            order by seq asc
            """,
            (task_id,),
        ).fetchall()


def test_replacement_protocol_splits_decision_and_preserves_task_id(tmp_path):
    case = _replacement_case(tmp_path)

    approval = case["coordinator"].approve(
        case["recommendation"],
        approved_by="controller",
        next_action="continue from replacement packet",
        required_artifacts=("artifact://patch",),
    )

    task_id = case["task_id"]
    with sqlite3.connect(case["db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        task = conn.execute("select * from tasks where task_id = ?", (task_id,)).fetchone()

    assert approval.task_id == task_id
    assert task["task_id"] == task_id
    assert task["status"] == TaskState.REASSIGNED.value
    assert task["assignee_agent_id"] == "runtime-helper-2"

    events = _replacement_events(case["db_path"], task_id)
    event_types = [row["type"] for row in events]
    assert event_types == [
        EventType.REPLACEMENT_RECOMMENDED.value,
        EventType.REPLACEMENT_APPROVAL_REQUESTED.value,
        EventType.REPLACEMENT_APPROVED.value,
        EventType.REPLACEMENT_REASSIGNMENT_COMMITTED.value,
    ]
    assert {row["correlation_id"] for row in events} == {case["recommendation"].recommendation_id}
    committed_payload = json.loads(events[-1]["payload_json"])
    assert committed_payload["task_id"] == task_id
    assert committed_payload["original_task_id"] == task_id
    assert committed_payload["old_agent_id"] == "worker.frontend"
    assert committed_payload["replacement_agent_id"] == "runtime-helper-2"


def test_replacement_rehydrates_new_session_and_invalidates_only_old_task_binding(tmp_path):
    case = _replacement_case(tmp_path)

    approval = case["coordinator"].approve(case["recommendation"], approved_by="controller")

    with sqlite3.connect(case["db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        old_binding = conn.execute(
            "select * from task_context_bindings where context_packet_id = ?",
            (case["old_assignment_packet_id"],),
        ).fetchone()
        unrelated_binding = conn.execute(
            "select * from task_context_bindings where context_packet_id = ?",
            (case["unrelated_packet_id"],),
        ).fetchone()
        replacement_binding = conn.execute(
            "select * from task_context_bindings where context_packet_id = ?",
            (approval.context_packet.packet_id,),
        ).fetchone()

    assert old_binding["status"] == BindingStatus.INVALIDATED.value
    assert unrelated_binding["status"] == BindingStatus.ACTIVE.value
    assert approval.context_packet.task_id == case["task_id"]
    assert approval.context_packet.agent_id == "runtime-helper-2"
    assert approval.context_packet.packet_kind == PacketKind.REHYDRATION
    assert approval.context_packet.instructions["invalidated_packet_ids"] == [case["old_assignment_packet_id"]]
    assert replacement_binding["status"] == BindingStatus.ACTIVE.value
    assert replacement_binding["binding_kind"] == PacketKind.REHYDRATION.value
    assert replacement_binding["session_id"] == case["replacement_session"].session_id


def test_replaced_old_session_cannot_continue_claims(tmp_path):
    case = _replacement_case(tmp_path)

    case["coordinator"].approve(case["recommendation"], approved_by="controller")

    with sqlite3.connect(case["db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        fence = conn.execute(
            "select active, session_role, replaced_by_session_id from session_fences where session_id = ?",
            (case["old_session"].session_id,),
        ).fetchone()

    assert fence["active"] == 0
    assert fence["session_role"] == SessionRole.REPLACED.value
    assert fence["replaced_by_session_id"] == case["replacement_session"].session_id

    with pytest.raises(PermissionError):
        case["board"].acknowledge_task(
            case["task_id"],
            actor=case["old_session"].agent_id,
            principal=agent_principal(case["old_session"].agent_id, session_id=case["old_session"].session_id),
            session_id=case["old_fence"].session_id,
            session_epoch=case["old_fence"].session_epoch,
            fencing_token=case["old_fence"].raw_token,
        )
