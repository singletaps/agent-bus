from __future__ import annotations

import pytest

from agent_bus.authority import controller_principal
from agent_bus.gates import GateBoard
from agent_bus.inbox import InboxStore
from agent_bus.models import GateState
from agent_bus.store import EventStore
from agent_bus.tasks import TaskBoard


def test_gate_contract_fields_round_trip_and_decision_actor_is_recorded(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    gates = GateBoard(db_path=db_path, principal=controller_principal())

    gate = gates.create_gate(
        "Contract acceptance",
        run_id="run-1",
        task_id="task-1",
        requested_by="runtime-worker-5",
        gate_kind="contract_acceptance",
        checklist=["schema migrated", "evidence linked"],
    )
    approved = gates.approve_gate(gate.gate_id, actor="controller")
    reloaded = gates.get_gate(gate.gate_id)

    assert reloaded.gate_kind == "contract_acceptance"
    assert reloaded.checklist == ["schema migrated", "evidence linked"]
    assert reloaded.required_evidence == []
    assert approved.state is GateState.APPROVED
    assert reloaded.decision_actor == "controller"
    assert reloaded.decision_by == "controller"


def test_high_risk_gate_escalates_for_qa_and_controller_approval_requires_related_evidence(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    tasks = TaskBoard(db_path=db_path, principal=controller_principal())
    evidence = tasks.create_artifact(
        "qa-report",
        "coordination/qa-report.txt",
        run_id="run-1",
        task_id="task-1",
        created_by="runtime-qa",
    )
    gates = GateBoard(db_path=db_path, principal=controller_principal())
    gate = gates.create_gate(
        "High risk release decision",
        run_id="run-1",
        task_id="task-1",
        owner_agent_id="runtime-qa",
        requested_by="runtime-worker-5",
        risk="high",
        gate_kind="release_gate",
        required_evidence=[evidence.artifact_id],
    )

    escalated = gates.approve_gate(gate.gate_id, actor="runtime-qa", evidence_artifact_ids=[evidence.artifact_id])

    assert escalated.state is GateState.ESCALATED
    controller_items = InboxStore(db_path).list_items("controller")
    assert controller_items[0].kind == "gate_approval_required"
    assert controller_items[0].payload["gate_id"] == gate.gate_id

    with pytest.raises(PermissionError, match="required evidence missing"):
        gates.approve_gate(gate.gate_id, actor="controller")

    approved = gates.approve_gate(gate.gate_id, actor="controller", evidence_artifact_ids=[evidence.artifact_id])

    assert approved.state is GateState.APPROVED
    assert approved.decision_actor == "controller"
    gate_events = EventStore(db_path).query_events(task_id="task-1")
    assert "gate.escalated" in [event.type for event in gate_events]
    assert "gate.approved" in [event.type for event in gate_events]


def test_gate_approval_rejects_unrelated_required_evidence(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    tasks = TaskBoard(db_path=db_path, principal=controller_principal())
    unrelated = tasks.create_artifact(
        "other-task-report",
        "coordination/other-task-report.txt",
        run_id="run-1",
        task_id="task-elsewhere",
        created_by="runtime-qa",
    )
    gates = GateBoard(db_path=db_path, principal=controller_principal())
    gate = gates.create_gate(
        "Evidence-bound decision",
        run_id="run-1",
        task_id="task-1",
        requested_by="runtime-worker-5",
        required_evidence=[unrelated.artifact_id],
    )

    with pytest.raises(PermissionError, match="required evidence is unrelated"):
        gates.approve_gate(gate.gate_id, actor="controller", evidence_artifact_ids=[unrelated.artifact_id])

    assert gates.get_gate(gate.gate_id).state is GateState.OPEN


def test_gate_approval_rejects_self_review_by_requester(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    gates = GateBoard(db_path=db_path, principal=controller_principal())
    gate = gates.create_gate("Self approval", task_id="task-1", requested_by="runtime-worker-5")

    with pytest.raises(PermissionError, match="reviewer cannot approve their own work"):
        gates.approve_gate(gate.gate_id, actor="runtime-worker-5")

    assert gates.get_gate(gate.gate_id).state is GateState.OPEN
