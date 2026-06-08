from __future__ import annotations

import json

from agent_bus.authority import controller_principal
from agent_bus.context import ContextStore
from agent_bus.gates import GateBoard
from agent_bus.models import TaskState
from agent_bus.protocol_models import ClaimStatus, FencingResult, ProjectionEffect
from agent_bus.tasks import TaskBoard
from agent_bus.cli import main


def _stdout_json(capsys):
    return json.loads(capsys.readouterr().out)


def test_cli_worker_task_complete_and_protocol_events_show_legacy_audit(tmp_path, capsys):
    db_path = tmp_path / "agent-bus.sqlite3"
    board = TaskBoard(db_path=db_path, principal=controller_principal())
    task = board.create_task("CLI protocol v2", owner_agent_id="controller")
    assigned = board.assign_task(task.task_id, "worker.backend", actor="controller")

    assert (
        main(
            [
                "worker",
                "task",
                "complete",
                assigned.task_id,
                "--actor",
                "worker.backend",
                "--db",
                str(db_path),
                "--json",
            ]
        )
        == 0
    )
    worker_claim = _stdout_json(capsys)
    assert worker_claim["claim"]["status"] == ClaimStatus.NEEDS_FENCING.value
    assert worker_claim["projection_effect"] == ProjectionEffect.AUDIT_ONLY.value
    assert worker_claim["fencing_result"] == FencingResult.MISSING.value
    assert worker_claim["task"]["status"] == TaskState.ASSIGNED.value

    assert main(["task", "complete", assigned.task_id, "--actor", "worker.backend", "--db", str(db_path), "--json"]) == 0
    legacy_claim = _stdout_json(capsys)
    assert legacy_claim["deprecated_adapter"]["type"] == "adapter.deprecated_path_used"
    assert legacy_claim["claim"]["status"] == ClaimStatus.NEEDS_FENCING.value

    assert (
        main(
            [
                "protocol",
                "events",
                "--type",
                "adapter.deprecated_path_used",
                "--db",
                str(db_path),
                "--json",
            ]
        )
        == 0
    )
    protocol_events = _stdout_json(capsys)["events"]
    assert protocol_events[-1]["payload"]["path"] == "cli.task.complete"
    assert protocol_events[-1]["projection_effect"] == ProjectionEffect.AUDIT_ONLY.value
    assert protocol_events[-1]["fencing_result"] == FencingResult.NOT_REQUIRED.value


def test_cli_controller_gate_approve_uses_canonical_group(tmp_path, capsys):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    board = TaskBoard(db_path=db_path, principal=controller)
    run = board.create_run("CLI controller", objective="split CLI", created_by="controller")
    task = board.create_task(
        "Approve with controller group",
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
    gate = GateBoard(db_path=db_path, principal=controller).create_gate(
        "CLI gate",
        run_id=run.run_id,
        task_id=task.task_id,
        requested_by="worker.backend",
        required_evidence=[evidence.artifact_id],
    )

    assert (
        main(
            [
                "controller",
                "gate",
                "approve",
                gate.gate_id,
                "--evidence-artifact-id",
                evidence.artifact_id,
                "--db",
                str(db_path),
                "--json",
            ]
        )
        == 0
    )
    output = _stdout_json(capsys)
    assert output["gate"]["state"] == "approved"
    assert output["gate"]["decision_actor"] == "controller"


def test_cli_user_interrupt_group_and_legacy_interrupt_audit(tmp_path, capsys):
    db_path = tmp_path / "agent-bus.sqlite3"
    context = ContextStore(db_path, principal=controller_principal())
    packet = context.create_packet(
        agent_id="worker.owner",
        task_id="task-1",
        run_id="run-1",
        summary="interrupt target",
        actor="controller",
    )

    assert (
        main(
            [
                "user",
                "interrupt",
                "create",
                "--actor",
                "user",
                "--text",
                "pause",
                "--run-id",
                "run-1",
                "--task-id",
                "task-1",
                "--task-owner",
                "worker.owner",
                "--db",
                str(db_path),
                "--json",
            ]
        )
        == 0
    )
    user_interrupt = _stdout_json(capsys)
    assert user_interrupt["result"]["invalidated_packet_ids_by_agent"]["worker.owner"] == [packet.packet_id]

    assert (
        main(
            [
                "interrupt",
                "create",
                "--actor",
                "user",
                "--text",
                "legacy pause",
                "--agent",
                "worker.extra",
                "--db",
                str(db_path),
                "--json",
            ]
        )
        == 0
    )
    legacy_interrupt = _stdout_json(capsys)
    assert legacy_interrupt["deprecated_adapter"]["payload"]["path"] == "cli.interrupt.create"
