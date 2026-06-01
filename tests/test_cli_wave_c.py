from __future__ import annotations

import json

from agent_bus.agents import AgentDirectory
from agent_bus.cli import build_parser, main
from agent_bus.context import ContextStore
from agent_bus.models import AgentRuntimeState


def _stdout_json(capsys):
    return json.loads(capsys.readouterr().out)


def _stderr_json(capsys):
    return json.loads(capsys.readouterr().err)


def test_required_operational_commands_accept_json_flag():
    parser = build_parser()
    commands = [
        ["init", "--json"],
        ["serve", "--json"],
        ["seed", "--json"],
        ["agent", "register", "worker", "--json"],
        ["wait", "--agent", "worker", "--json"],
        ["ack", "inbox_1", "--json"],
        ["context", "get", "ctx_1", "--json"],
        ["task", "create", "Do work", "--json"],
        ["task", "progress", "task_1", "--json"],
        ["task", "complete", "task_1", "--json"],
        ["task", "fail", "task_1", "--reason", "bad", "--json"],
        ["review", "request", "--task-id", "task_1", "--reviewer", "qa", "--json"],
        [
            "review",
            "submit",
            "--task-id",
            "task_1",
            "--worker",
            "worker",
            "--severity",
            "P1",
            "--category",
            "test",
            "--evidence",
            "missing test",
            "--requested-change",
            "add test",
            "--json",
        ],
        ["gate", "approve", "gate_1", "--json"],
        ["gate", "reject", "gate_1", "--json"],
        ["gate", "escalate", "gate_1", "--json"],
        ["interrupt", "create", "--task-owner", "worker", "--json"],
        ["replacement", "approve", "--old-session-id", "ses_1", "--task-id", "task_1", "--json"],
        ["artifact", "create", "log", "file://test.log", "--json"],
    ]

    for argv in commands:
        args = parser.parse_args(argv)
        assert getattr(args, "json") is True, argv


def test_cli_operational_flow_persists_json_outputs_and_exit_codes(tmp_path, capsys):
    db_path = tmp_path / "agent-bus.sqlite3"

    assert main(["init", "--reset", "--db", str(db_path), "--json"]) == 0
    assert _stdout_json(capsys)["ok"] is True

    assert (
        main(
            [
                "agent",
                "register",
                "worker",
                "--role",
                "worker",
                "--capability",
                "python",
                "--db",
                str(db_path),
                "--json",
            ]
        )
        == 0
    )
    worker_registration = _stdout_json(capsys)
    worker_session_id = worker_registration["session"]["session_id"]

    assert main(["agent", "register", "worker.spare", "--capability", "python", "--db", str(db_path), "--json"]) == 0
    _stdout_json(capsys)

    assert (
        main(
            [
                "task",
                "create",
                "Implement CLI flow",
                "--run-title",
                "CLI run",
                "--owner",
                "controller",
                "--assignee",
                "worker",
                "--priority",
                "70",
                "--db",
                str(db_path),
                "--json",
            ]
        )
        == 0
    )
    task_created = _stdout_json(capsys)
    task_id = task_created["task"]["task_id"]
    run_id = task_created["run"]["run_id"]
    assert task_created["task"]["status"] == "assigned"

    context = ContextStore(db_path)
    packet = context.create_packet(agent_id="worker", task_id=task_id, run_id=run_id, summary="CLI context")
    context.close()

    assert main(["context", "get", packet.packet_id, "--db", str(db_path), "--json"]) == 0
    assert _stdout_json(capsys)["packet"]["summary"] == "CLI context"

    assert main(["wait", "--agent", "worker", "--timeout", "0.01", "--db", str(db_path), "--json"]) == 0
    delivered = _stdout_json(capsys)
    assert delivered["item"]["kind"] == "task_assigned"

    assert main(["ack", delivered["item"]["inbox_id"], "--agent", "worker", "--db", str(db_path), "--json"]) == 0
    assert _stdout_json(capsys)["acked"] is True

    assert main(["task", "progress", task_id, "--actor", "worker", "--db", str(db_path), "--json"]) == 0
    assert _stdout_json(capsys)["task"]["status"] == "working"

    assert main(["task", "complete", task_id, "--actor", "worker", "--db", str(db_path), "--json"]) == 0
    assert _stdout_json(capsys)["task"]["status"] == "completed"

    assert (
        main(
            [
                "review",
                "request",
                "--task-id",
                task_id,
                "--reviewer",
                "qa",
                "--requester",
                "worker",
                "--db",
                str(db_path),
                "--json",
            ]
        )
        == 0
    )
    assert _stdout_json(capsys)["item"]["kind"] == "review_requested"

    assert (
        main(
            [
                "review",
                "submit",
                "--task-id",
                task_id,
                "--worker",
                "worker",
                "--reviewer",
                "qa",
                "--severity",
                "P1",
                "--category",
                "behavior",
                "--evidence",
                "CLI behavior gap",
                "--requested-change",
                "wire command",
                "--blocking",
                "--db",
                str(db_path),
                "--json",
            ]
        )
        == 0
    )
    finding_id = _stdout_json(capsys)["findings"][0]["finding_id"]

    assert main(["review", "resolve", finding_id, "--resolved-by", "worker", "--db", str(db_path), "--json"]) == 0
    assert _stdout_json(capsys)["finding"]["status"] == "resolved"

    assert main(["gate", "create", "CLI gate", "--run-id", run_id, "--owner", "qa", "--db", str(db_path), "--json"]) == 0
    gate_id = _stdout_json(capsys)["gate"]["gate_id"]
    assert main(["gate", "approve", gate_id, "--actor", "controller", "--db", str(db_path), "--json"]) == 0
    assert _stdout_json(capsys)["gate"]["state"] == "approved"

    assert (
        main(
            [
                "artifact",
                "create",
                "test-log",
                "file://test.log",
                "--run-id",
                run_id,
                "--task-id",
                task_id,
                "--metadata-json",
                '{"passed": true}',
                "--db",
                str(db_path),
                "--json",
            ]
        )
        == 0
    )
    assert _stdout_json(capsys)["artifact"]["metadata"] == {"passed": True}

    assert (
        main(
            [
                "interrupt",
                "create",
                "--actor",
                "user",
                "--text",
                "replan",
                "--run-id",
                run_id,
                "--task-id",
                task_id,
                "--task-owner",
                "worker",
                "--db",
                str(db_path),
                "--json",
            ]
        )
        == 0
    )
    interrupted = _stdout_json(capsys)
    assert "worker" in interrupted["result"]["affected_agents"]
    assert interrupted["result"]["invalidated_packet_ids_by_agent"]["worker"] == [packet.packet_id]

    directory = AgentDirectory(db_path=db_path)
    directory.update_session_state(worker_session_id, AgentRuntimeState.CONTEXT_LOST, reason="lost context")
    directory.close()

    assert (
        main(
            [
                "replacement",
                "approve",
                "--old-session-id",
                worker_session_id,
                "--task-id",
                task_id,
                "--run-id",
                run_id,
                "--candidate-agent",
                "worker.spare",
                "--required-capability",
                "python",
                "--db",
                str(db_path),
                "--json",
            ]
        )
        == 0
    )
    replacement = _stdout_json(capsys)
    assert replacement["approval"]["replacement_session"]["agent_id"] == "worker.spare"
    assert replacement["approval"]["context_packet"]["task_id"] == task_id

    assert main(["ack", "missing", "--db", str(db_path), "--json"]) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False
    assert error["inbox_id"] == "missing"


def test_seed_creates_default_agents_and_wait_items(tmp_path, capsys):
    db_path = tmp_path / "agent-bus.sqlite3"

    assert main(["seed", "--reset", "--db", str(db_path), "--json"]) == 0
    seeded = _stdout_json(capsys)

    assert seeded["ok"] is True
    assert set(seeded["sessions"]) == {
        "controller",
        "observer",
        "worker.frontend",
        "worker.backend",
        "qa",
        "worker.spare",
    }

    assert main(["wait", "--agent", "controller", "--timeout", "0.01", "--db", str(db_path), "--json"]) == 0
    assert _stdout_json(capsys)["item"]["kind"] == "run_seeded"

    assert main(["wait", "--agent", "worker.frontend", "--timeout", "0.01", "--db", str(db_path), "--json"]) == 0
    assert _stdout_json(capsys)["item"]["kind"] == "task_assigned"

    assert main(["wait", "--agent", "qa", "--timeout", "0.01", "--db", str(db_path), "--json"]) == 0
    assert _stdout_json(capsys)["item"]["kind"] == "review_requested"


def test_artifact_metadata_json_accepts_at_file_reference_for_powershell(tmp_path, capsys):
    db_path = tmp_path / "agent-bus.sqlite3"
    metadata_path = tmp_path / "artifact-metadata.json"
    metadata_path.write_text(
        json.dumps({"passed": True, "commands": ["wait", "ack", "artifact"]}),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "artifact",
                "create",
                "live-test-report",
                "agent-bus://tests/metadata-json",
                "--metadata-json",
                f"@{metadata_path}",
                "--db",
                str(db_path),
                "--json",
            ]
        )
        == 0
    )
    artifact = _stdout_json(capsys)["artifact"]
    assert artifact["metadata"] == {"passed": True, "commands": ["wait", "ack", "artifact"]}


def test_artifact_metadata_json_malformed_returns_structured_usage_error(tmp_path, capsys):
    db_path = tmp_path / "agent-bus.sqlite3"

    assert (
        main(
            [
                "artifact",
                "create",
                "live-test-report",
                "agent-bus://tests/bad-metadata-json",
                "--metadata-json",
                "{bad",
                "--db",
                str(db_path),
                "--json",
            ]
        )
        == 2
    )
    error = _stderr_json(capsys)
    assert error["ok"] is False
    assert error["error"] == "cli_error"
    assert error["message"].startswith("--metadata-json must be valid JSON")
