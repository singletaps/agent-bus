from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sqlite3
import sys
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from . import __version__


EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_USAGE_ERROR = 2
EXIT_CONTEXT_INVALIDATED = 3


class CliError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: int = EXIT_RUNTIME_ERROR,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.payload = payload or {}


class CliUsageError(CliError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code=EXIT_USAGE_ERROR)


class AgentBusArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = AgentBusArgumentParser(
        prog="agent-bus",
        description="Durable local Agent Bus runtime for persistent Codex workers.",
    )
    parser.add_argument("--version", action="version", version=f"agent-bus {__version__}")
    _add_json(parser)

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="COMMAND",
        parser_class=AgentBusArgumentParser,
    )

    init_parser = subparsers.add_parser("init", help="initialize the local Agent Bus store")
    init_parser.add_argument("--reset", action="store_true", help="reset existing local state before initialization")
    _add_db(init_parser)
    _add_json(init_parser)

    serve_parser = subparsers.add_parser("serve", help="serve the Agent Bus API and console")
    serve_parser.add_argument("--host", default="127.0.0.1", help="host interface to bind")
    serve_parser.add_argument("--port", default=8765, type=int, help="port to bind")
    serve_parser.add_argument("--log-level", default="info", help="uvicorn log level")
    _add_db(serve_parser)
    _add_json(serve_parser)

    seed_parser = subparsers.add_parser("seed", help="seed a small operational demo run")
    seed_parser.add_argument("--reset", action="store_true", help="reset the database before seeding")
    _add_db(seed_parser)
    _add_json(seed_parser)

    agent_parser = subparsers.add_parser("agent", help="manage agent identities and sessions")
    _add_json(agent_parser)
    agent_subparsers = agent_parser.add_subparsers(
        dest="agent_command",
        metavar="AGENT_COMMAND",
        parser_class=AgentBusArgumentParser,
    )
    register_parser = agent_subparsers.add_parser("register", help="register an agent identity")
    register_parser.add_argument("agent_id", help="stable agent identity")
    register_parser.add_argument("--role", help="agent role")
    register_parser.add_argument("--display-name", help="human readable agent name")
    register_parser.add_argument("--capability", action="append", default=[], help="declared capability name")
    register_parser.add_argument("--run-id", help="run id for the started session")
    register_parser.add_argument("--session-id", help="explicit session id")
    register_parser.add_argument("--state", default="STANDBY_READY", help="initial session runtime state")
    register_parser.add_argument("--no-session", action="store_true", help="register identity without starting a session")
    _add_db(register_parser)
    _add_json(register_parser)

    wait_parser = subparsers.add_parser("wait", help="wait for the next visible inbox item")
    wait_parser.add_argument("--agent", required=True, help="agent identity to wait as")
    wait_parser.add_argument("--timeout", default=300.0, type=float, help="seconds to wait before returning noop")
    wait_parser.add_argument("--busy", action="store_true", help="only deliver urgent control items")
    _add_db(wait_parser)
    _add_json(wait_parser)

    ack_parser = subparsers.add_parser("ack", help="acknowledge an inbox item")
    ack_parser.add_argument("inbox_id", help="inbox item id to acknowledge")
    ack_parser.add_argument("--agent", help="agent identity expected to own the item")
    _add_db(ack_parser)
    _add_json(ack_parser)

    context_parser = subparsers.add_parser("context", help="inspect context packets")
    _add_json(context_parser)
    context_subparsers = context_parser.add_subparsers(
        dest="context_command",
        metavar="CONTEXT_COMMAND",
        parser_class=AgentBusArgumentParser,
    )
    context_get = context_subparsers.add_parser("get", help="fetch a context packet")
    context_get.add_argument("packet_id", help="context packet id")
    context_get.add_argument("--include-inactive", action="store_true", help="return invalidated or superseded packets")
    _add_db(context_get)
    _add_json(context_get)

    task_parser = subparsers.add_parser("task", help="manage runs, tasks, and artifacts")
    _add_json(task_parser)
    task_subparsers = task_parser.add_subparsers(
        dest="task_command",
        metavar="TASK_COMMAND",
        parser_class=AgentBusArgumentParser,
    )
    task_create = task_subparsers.add_parser("create", help="create a task")
    task_create.add_argument("title", help="task title")
    task_create.add_argument("--run-id", help="existing run id")
    task_create.add_argument("--run-title", help="create a new run with this title and attach the task")
    task_create.add_argument("--objective", default="", help="objective for a created run")
    task_create.add_argument("--owner", help="owner agent id")
    task_create.add_argument("--assignee", help="assignee agent id")
    task_create.add_argument("--priority", default=0, type=int, help="task priority")
    task_create.add_argument("--parent-task-id", help="parent task id")
    _add_db(task_create)
    _add_json(task_create)

    task_ack = task_subparsers.add_parser("ack", help="mark an assigned task acknowledged")
    task_ack.add_argument("task_id")
    task_ack.add_argument("--actor", help="agent acknowledging the task")
    _add_db(task_ack)
    _add_json(task_ack)

    task_progress = task_subparsers.add_parser("progress", help="mark a task as working")
    task_progress.add_argument("task_id")
    task_progress.add_argument("--actor", help="agent progressing the task")
    _add_db(task_progress)
    _add_json(task_progress)

    task_complete = task_subparsers.add_parser("complete", help="mark a task complete")
    task_complete.add_argument("task_id")
    task_complete.add_argument("--actor", help="agent completing the task")
    _add_db(task_complete)
    _add_json(task_complete)

    task_fail = task_subparsers.add_parser("fail", help="mark a task failed")
    task_fail.add_argument("task_id")
    task_fail.add_argument("--reason", required=True, help="failure reason")
    task_fail.add_argument("--actor", help="agent failing the task")
    _add_db(task_fail)
    _add_json(task_fail)

    worker_parser = subparsers.add_parser("worker", help="worker-scoped runtime commands")
    worker_subparsers = worker_parser.add_subparsers(
        dest="worker_command",
        metavar="WORKER_COMMAND",
        parser_class=AgentBusArgumentParser,
        required=True,
    )
    worker_task = worker_subparsers.add_parser("task", help="worker task claims")
    worker_task_subparsers = worker_task.add_subparsers(
        dest="worker_task_command",
        metavar="WORKER_TASK_COMMAND",
        parser_class=AgentBusArgumentParser,
        required=True,
    )
    worker_task_complete = worker_task_subparsers.add_parser("complete", help="claim task completion")
    worker_task_complete.add_argument("task_id")
    worker_task_complete.add_argument("--actor", required=True, help="worker agent id")
    worker_task_complete.add_argument("--session-id")
    worker_task_complete.add_argument("--session-epoch", type=int)
    worker_task_complete.add_argument("--context-packet-id")
    _add_db(worker_task_complete)
    _add_json(worker_task_complete)
    worker_inbox = worker_subparsers.add_parser("inbox", help="fenced worker inbox operations")
    worker_inbox_subparsers = worker_inbox.add_subparsers(
        dest="worker_inbox_command",
        metavar="WORKER_INBOX_COMMAND",
        parser_class=AgentBusArgumentParser,
        required=True,
    )
    worker_inbox_wait = worker_inbox_subparsers.add_parser("wait", help="wait for inbox with fencing")
    worker_inbox_wait.add_argument("--agent", required=True)
    worker_inbox_wait.add_argument("--session-id", required=True)
    worker_inbox_wait.add_argument("--session-epoch", type=int, required=True)
    worker_inbox_wait.add_argument("--fencing-token", required=True)
    worker_inbox_wait.add_argument("--timeout", default=300.0, type=float)
    worker_inbox_wait.add_argument("--busy", action="store_true")
    _add_db(worker_inbox_wait)
    _add_json(worker_inbox_wait)
    worker_inbox_ack = worker_inbox_subparsers.add_parser("ack", help="ack inbox item with fencing")
    worker_inbox_ack.add_argument("inbox_id")
    worker_inbox_ack.add_argument("--agent", required=True)
    worker_inbox_ack.add_argument("--session-id", required=True)
    worker_inbox_ack.add_argument("--session-epoch", type=int, required=True)
    worker_inbox_ack.add_argument("--fencing-token", required=True)
    _add_db(worker_inbox_ack)
    _add_json(worker_inbox_ack)

    controller_parser = subparsers.add_parser("controller", help="controller-scoped commands")
    controller_subparsers = controller_parser.add_subparsers(
        dest="controller_command",
        metavar="CONTROLLER_COMMAND",
        parser_class=AgentBusArgumentParser,
        required=True,
    )
    controller_gate = controller_subparsers.add_parser("gate", help="controller gate decisions")
    controller_gate_subparsers = controller_gate.add_subparsers(
        dest="controller_gate_command",
        metavar="CONTROLLER_GATE_COMMAND",
        parser_class=AgentBusArgumentParser,
        required=True,
    )
    for command_name in ("approve", "reject", "escalate"):
        controller_gate_action = controller_gate_subparsers.add_parser(command_name, help=f"{command_name} a gate")
        controller_gate_action.add_argument("gate_id")
        controller_gate_action.add_argument("--reason")
        if command_name == "approve":
            controller_gate_action.add_argument("--allow-high-risk", action="store_true")
            controller_gate_action.add_argument("--action-agent", default="controller")
            controller_gate_action.add_argument("--evidence-artifact-id", action="append", default=[])
        _add_db(controller_gate_action)
        _add_json(controller_gate_action)
    controller_claim = controller_subparsers.add_parser("task-claim", help="controller task claim decisions")
    controller_claim_subparsers = controller_claim.add_subparsers(
        dest="controller_claim_command",
        metavar="CONTROLLER_CLAIM_COMMAND",
        parser_class=AgentBusArgumentParser,
        required=True,
    )
    controller_claim_commit = controller_claim_subparsers.add_parser("commit", help="commit a worker task claim")
    controller_claim_commit.add_argument("claim_id")
    _add_db(controller_claim_commit)
    _add_json(controller_claim_commit)

    user_parser = subparsers.add_parser("user", help="user-scoped commands")
    user_subparsers = user_parser.add_subparsers(
        dest="user_command",
        metavar="USER_COMMAND",
        parser_class=AgentBusArgumentParser,
        required=True,
    )
    user_interrupt = user_subparsers.add_parser("interrupt", help="user interrupts")
    user_interrupt_subparsers = user_interrupt.add_subparsers(
        dest="user_interrupt_command",
        metavar="USER_INTERRUPT_COMMAND",
        parser_class=AgentBusArgumentParser,
        required=True,
    )
    user_interrupt_create = user_interrupt_subparsers.add_parser("create", help="create and route a user interrupt")
    _add_interrupt_create_arguments(user_interrupt_create)

    review_parser = subparsers.add_parser("review", help="request and submit code review findings")
    _add_json(review_parser)
    review_subparsers = review_parser.add_subparsers(
        dest="review_command",
        metavar="REVIEW_COMMAND",
        parser_class=AgentBusArgumentParser,
    )
    review_request = review_subparsers.add_parser("request", help="enqueue a review request")
    review_request.add_argument("--task-id", required=True)
    review_request.add_argument("--reviewer", required=True, help="agent that should review")
    review_request.add_argument("--requester", help="agent requesting review")
    review_request.add_argument("--worker", help="worker whose task is under review")
    review_request.add_argument("--run-id", help="run id")
    review_request.add_argument("--note", default="", help="review request note")
    review_request.add_argument("--context-packet-id", help="context packet for the reviewer")
    review_request.add_argument("--priority", default=70, type=int)
    _add_db(review_request)
    _add_json(review_request)

    review_submit = review_subparsers.add_parser("submit", help="submit findings and request changes")
    review_submit.add_argument("--task-id", required=True)
    review_submit.add_argument("--worker", required=True, help="worker agent receiving findings")
    review_submit.add_argument("--reviewer", help="reviewer agent id")
    review_submit.add_argument("--run-id", help="run id")
    _add_finding_arguments(review_submit)
    _add_db(review_submit)
    _add_json(review_submit)

    review_resolve = review_subparsers.add_parser("resolve", help="resolve one review finding")
    review_resolve.add_argument("finding_id")
    review_resolve.add_argument("--resolved-by", required=True)
    review_resolve.add_argument("--status", default="resolved", choices=["resolved", "dismissed"])
    _add_db(review_resolve)
    _add_json(review_resolve)

    gate_parser = subparsers.add_parser("gate", help="manage gates")
    _add_json(gate_parser)
    gate_subparsers = gate_parser.add_subparsers(
        dest="gate_command",
        metavar="GATE_COMMAND",
        parser_class=AgentBusArgumentParser,
    )
    gate_create = gate_subparsers.add_parser("create", help="create a gate")
    gate_create.add_argument("name")
    gate_create.add_argument("--run-id")
    gate_create.add_argument("--task-id")
    gate_create.add_argument("--owner")
    gate_create.add_argument("--requested-by")
    gate_create.add_argument("--risk", default="normal")
    gate_create.add_argument("--gate-kind", default="approval")
    gate_create.add_argument("--checklist", action="append", default=[])
    gate_create.add_argument("--required-evidence", action="append", default=[])
    _add_db(gate_create)
    _add_json(gate_create)
    for command_name in ("approve", "reject", "escalate"):
        gate_action = gate_subparsers.add_parser(command_name, help=f"{command_name} a gate")
        gate_action.add_argument("gate_id")
        gate_action.add_argument("--actor", default="controller")
        gate_action.add_argument("--reason")
        gate_action.add_argument("--as-controller", action="store_true")
        if command_name == "approve":
            gate_action.add_argument("--allow-high-risk", action="store_true")
            gate_action.add_argument("--action-agent", default="controller")
            gate_action.add_argument("--evidence-artifact-id", action="append", default=[])
        gate_action.set_defaults(
            deprecated_adapter_path=f"cli.gate.{command_name}",
            deprecated_adapter_replacement=f"cli.controller.gate.{command_name}",
        )
        _add_db(gate_action)
        _add_json(gate_action)

    interrupt_parser = subparsers.add_parser("interrupt", help="create human/user interrupts")
    _add_json(interrupt_parser)
    interrupt_subparsers = interrupt_parser.add_subparsers(
        dest="interrupt_command",
        metavar="INTERRUPT_COMMAND",
        parser_class=AgentBusArgumentParser,
    )
    interrupt_create = interrupt_subparsers.add_parser("create", help="create and route an interrupt")
    _add_interrupt_create_arguments(interrupt_create)
    interrupt_create.set_defaults(
        deprecated_adapter_path="cli.interrupt.create",
        deprecated_adapter_replacement="cli.user.interrupt.create",
    )

    replacement_parser = subparsers.add_parser("replacement", help="approve replacement handoffs")
    _add_json(replacement_parser)
    replacement_subparsers = replacement_parser.add_subparsers(
        dest="replacement_command",
        metavar="REPLACEMENT_COMMAND",
        parser_class=AgentBusArgumentParser,
    )
    replacement_approve = replacement_subparsers.add_parser("approve", help="approve a replacement recommendation")
    replacement_approve.add_argument("--old-session-id", required=True)
    replacement_approve.add_argument("--task-id", required=True)
    replacement_approve.add_argument("--run-id")
    replacement_approve.add_argument("--candidate-agent")
    replacement_approve.add_argument("--candidate-session-id")
    replacement_approve.add_argument("--required-capability", action="append", default=[])
    replacement_approve.add_argument("--role")
    replacement_approve.add_argument("--approved-by", default="controller")
    replacement_approve.add_argument("--next-action", default="continue the same task from the rehydration packet")
    replacement_approve.add_argument("--artifact", action="append", default=[], help="required artifact URI")
    replacement_approve.add_argument("--invalidated-packet-id", action="append", default=[])
    _add_db(replacement_approve)
    _add_json(replacement_approve)

    artifact_parser = subparsers.add_parser("artifact", help="manage task artifacts")
    _add_json(artifact_parser)
    artifact_subparsers = artifact_parser.add_subparsers(
        dest="artifact_command",
        metavar="ARTIFACT_COMMAND",
        parser_class=AgentBusArgumentParser,
    )
    artifact_create = artifact_subparsers.add_parser("create", help="create an artifact record")
    artifact_create.add_argument("kind")
    artifact_create.add_argument("uri")
    artifact_create.add_argument("--run-id")
    artifact_create.add_argument("--task-id")
    artifact_create.add_argument("--created-by")
    artifact_create.add_argument("--metadata-json", help="metadata JSON object, or @path to a JSON object file")
    _add_db(artifact_create)
    _add_json(artifact_create)

    protocol_parser = subparsers.add_parser("protocol", help="inspect protocol/audit events")
    protocol_subparsers = protocol_parser.add_subparsers(
        dest="protocol_command",
        metavar="PROTOCOL_COMMAND",
        parser_class=AgentBusArgumentParser,
        required=True,
    )
    protocol_events = protocol_subparsers.add_parser("events", help="list protocol events")
    protocol_events.add_argument("--type")
    protocol_events.add_argument("--limit", type=int)
    _add_db(protocol_events)
    _add_json(protocol_events)

    models_parser = subparsers.add_parser("models", help="print model availability diagnostics")
    _add_json(models_parser)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command is None:
            parser.print_help()
            return EXIT_OK
        return _dispatch(args)
    except CliError as exc:
        _emit_error(exc, as_json=_argv_wants_json(argv))
        return exc.code
    except KeyboardInterrupt:
        exc = CliError("interrupted", code=130)
        _emit_error(exc, as_json=_argv_wants_json(argv))
        return exc.code
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        cli_error = CliError(str(exc) or exc.__class__.__name__, payload={"exception": exc.__class__.__name__})
        _emit_error(cli_error, as_json=_argv_wants_json(argv))
        return cli_error.code


def _dispatch(args: argparse.Namespace) -> int:
    command = args.command
    if command == "init":
        return _handle_init(args)
    if command == "serve":
        return _handle_serve(args)
    if command == "seed":
        return _handle_seed(args)
    if command == "agent":
        if args.agent_command == "register":
            return _handle_agent_register(args)
        raise CliUsageError("agent requires a subcommand")
    if command == "wait":
        return _handle_wait(args)
    if command == "ack":
        return _handle_ack(args)
    if command == "context":
        if args.context_command == "get":
            return _handle_context_get(args)
        raise CliUsageError("context requires a subcommand")
    if command == "task":
        return _dispatch_task(args)
    if command == "worker":
        return _dispatch_worker(args)
    if command == "controller":
        return _dispatch_controller(args)
    if command == "user":
        return _dispatch_user(args)
    if command == "review":
        return _dispatch_review(args)
    if command == "gate":
        return _dispatch_gate(args)
    if command == "interrupt":
        if args.interrupt_command == "create":
            return _handle_interrupt_create(args)
        raise CliUsageError("interrupt requires a subcommand")
    if command == "replacement":
        if args.replacement_command == "approve":
            return _handle_replacement_approve(args)
        raise CliUsageError("replacement requires a subcommand")
    if command == "artifact":
        if args.artifact_command == "create":
            return _handle_artifact_create(args)
        raise CliUsageError("artifact requires a subcommand")
    if command == "protocol":
        if args.protocol_command == "events":
            return _handle_protocol_events(args)
        raise CliUsageError("protocol requires a subcommand")
    if command == "models":
        return _handle_models(args)
    raise CliUsageError(f"unknown command: {command}")


def _dispatch_task(args: argparse.Namespace) -> int:
    if args.task_command == "create":
        return _handle_task_create(args)
    if args.task_command == "ack":
        return _handle_task_ack(args)
    if args.task_command == "progress":
        return _handle_task_progress(args)
    if args.task_command == "complete":
        return _handle_task_complete(args)
    if args.task_command == "fail":
        return _handle_task_fail(args)
    raise CliUsageError("task requires a subcommand")


def _dispatch_worker(args: argparse.Namespace) -> int:
    if args.worker_command == "task" and args.worker_task_command == "complete":
        return _handle_worker_task_complete(args)
    if args.worker_command == "inbox":
        if args.worker_inbox_command == "wait":
            return _handle_worker_inbox_wait(args)
        if args.worker_inbox_command == "ack":
            return _handle_worker_inbox_ack(args)
    raise CliUsageError("worker requires a subcommand")


def _dispatch_controller(args: argparse.Namespace) -> int:
    if args.controller_command == "gate":
        if args.controller_gate_command == "approve":
            args.actor = "controller"
            return _handle_gate_approve(args)
        if args.controller_gate_command == "reject":
            args.actor = "controller"
            return _handle_gate_reject(args)
        if args.controller_gate_command == "escalate":
            args.actor = "controller"
            return _handle_gate_escalate(args)
    if args.controller_command == "task-claim" and args.controller_claim_command == "commit":
        return _handle_controller_task_claim_commit(args)
    raise CliUsageError("controller requires a subcommand")


def _dispatch_user(args: argparse.Namespace) -> int:
    if args.user_command == "interrupt" and args.user_interrupt_command == "create":
        return _handle_interrupt_create(args)
    raise CliUsageError("user requires a subcommand")


def _dispatch_review(args: argparse.Namespace) -> int:
    if args.review_command == "request":
        return _handle_review_request(args)
    if args.review_command == "submit":
        return _handle_review_submit(args)
    if args.review_command == "resolve":
        return _handle_review_resolve(args)
    raise CliUsageError("review requires a subcommand")


def _dispatch_gate(args: argparse.Namespace) -> int:
    if args.gate_command == "create":
        return _handle_gate_create(args)
    if args.gate_command == "approve":
        return _handle_gate_approve(args)
    if args.gate_command == "reject":
        return _handle_gate_reject(args)
    if args.gate_command == "escalate":
        return _handle_gate_escalate(args)
    raise CliUsageError("gate requires a subcommand")


def _handle_init(args: argparse.Namespace) -> int:
    db_path = _ensure_operational_schema(args.db, reset=args.reset)
    _emit({"ok": True, "db": str(db_path), "reset": bool(args.reset)}, as_json=_as_json(args))
    return EXIT_OK


def _handle_serve(args: argparse.Namespace) -> int:
    db_path = _ensure_operational_schema(args.db)
    os.environ["AGENT_BUS_DB"] = str(db_path)
    _emit(
        {"ok": True, "db": str(db_path), "host": args.host, "port": args.port, "serving": True},
        as_json=_as_json(args),
    )
    try:
        import uvicorn
        from . import server
    except ImportError as exc:
        raise CliError(f"serve requires the Wave C API server module: {exc}") from exc

    app = None
    factory = getattr(server, "create_app", None)
    if callable(factory):
        try:
            app = factory(db_path=db_path)
        except TypeError:
            app = factory()
    elif hasattr(server, "app"):
        app = server.app
    if app is None:
        raise CliError("agent_bus.server must expose create_app(...) or app")
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
    return EXIT_OK


def _handle_seed(args: argparse.Namespace) -> int:
    db_path = _ensure_operational_schema(args.db, reset=args.reset)
    from .agents import AgentDirectory
    from .authority import system_principal
    from .context import ContextStore
    from .gates import GateBoard
    from .inbox import InboxStore
    from .tasks import TaskBoard

    directory = AgentDirectory(db_path=db_path)
    principal = system_principal("cli-seed")
    board = TaskBoard(db_path=db_path, agent_directory=directory, principal=principal)
    context = ContextStore(db_path, principal=principal)
    inbox = InboxStore(db_path, principal=principal)
    gates = GateBoard(db_path=db_path)
    try:
        sessions = {}
        for agent_id, role, capabilities in (
            ("controller", "controller", ["planning", "coordination"]),
            ("observer", "observer", ["monitoring"]),
            ("worker.frontend", "worker", ["react", "frontend"]),
            ("worker.backend", "worker", ["python", "backend"]),
            ("qa", "qa", ["testing", "review"]),
            ("worker.spare", "worker", ["react", "python"]),
        ):
            directory.register_identity(agent_id, role=role, declared_capabilities=capabilities)
            active = directory.get_active_session(agent_id)
            sessions[agent_id] = active or directory.start_session(agent_id)

        run = board.create_run(
            "Seeded Agent Bus operations run",
            objective="Exercise wait, context, review, gate, interrupt, and replacement flows.",
            created_by="controller",
        )
        frontend = board.create_task(
            "Implement frontend operations console",
            run_id=run.run_id,
            owner_agent_id="controller",
            assignee_agent_id="worker.frontend",
            priority=60,
        )
        backend = board.create_task(
            "Implement backend runtime API",
            run_id=run.run_id,
            owner_agent_id="controller",
            assignee_agent_id="worker.backend",
            priority=60,
        )
        controller_packet = context.create_packet(
            agent_id="controller",
            run_id=run.run_id,
            summary="Seeded run is ready for controller planning.",
            instructions={"next_action": "review assigned frontend/backend tasks"},
            actor="seed",
        )
        frontend_packet = context.create_packet(
            agent_id="worker.frontend",
            task_id=frontend.task_id,
            run_id=run.run_id,
            summary="Frontend task assignment",
            instructions={"next_action": "acknowledge and start frontend work"},
            actor="seed",
        )
        backend_packet = context.create_packet(
            agent_id="worker.backend",
            task_id=backend.task_id,
            run_id=run.run_id,
            summary="Backend task assignment",
            instructions={"next_action": "acknowledge and start backend work"},
            actor="seed",
        )
        qa_packet = context.create_packet(
            agent_id="qa",
            run_id=run.run_id,
            summary="QA review request",
            instructions={"next_action": "watch task progress and gate readiness"},
            actor="seed",
        )
        gate = gates.create_gate(
            "Seeded Wave C QA gate",
            run_id=run.run_id,
            owner_agent_id="qa",
            requested_by="controller",
            risk="normal",
        )
        controller_item = inbox.enqueue(
            "controller",
            "run_seeded",
            {"run_id": run.run_id, "task_ids": [frontend.task_id, backend.task_id]},
            priority=100,
            context_packet_id=controller_packet.packet_id,
            dedupe_key=f"seed:{run.run_id}:controller",
        )
        qa_item = inbox.enqueue(
            "qa",
            "review_requested",
            {"run_id": run.run_id, "gate_id": gate.gate_id, "task_ids": [frontend.task_id, backend.task_id]},
            priority=75,
            context_packet_id=qa_packet.packet_id,
            dedupe_key=f"seed:{run.run_id}:qa",
        )
        payload = {
            "ok": True,
            "db": str(db_path),
            "run": run,
            "tasks": [frontend, backend],
            "gate": gate,
            "sessions": sessions,
            "context_packets": [controller_packet, frontend_packet, backend_packet, qa_packet],
            "inbox_items": [controller_item, qa_item],
        }
        _emit(payload, as_json=_as_json(args))
        return EXIT_OK
    finally:
        gates.close()
        inbox.close()
        context.close()
        board.close()
        directory.close()


def _handle_agent_register(args: argparse.Namespace) -> int:
    from .agents import AgentDirectory
    from .models import AgentRuntimeState, BusEvent, EventType
    from .store import EventStore

    directory = AgentDirectory(db_path=args.db)
    store = EventStore(args.db)
    try:
        identity = directory.register_identity(
            args.agent_id,
            display_name=args.display_name,
            role=args.role,
            declared_capabilities=args.capability,
        )
        registered = store.append_event(
            BusEvent(
                type=EventType.AGENT_REGISTERED,
                actor=args.agent_id,
                agent_id=args.agent_id,
                payload=identity.model_dump(mode="json"),
            )
        )
        session = None
        started = None
        if not args.no_session:
            session = directory.start_session(
                args.agent_id,
                run_id=args.run_id,
                session_id=args.session_id,
                runtime_state=AgentRuntimeState(args.state),
            )
            started = store.append_event(
                BusEvent(
                    type=EventType.AGENT_SESSION_STARTED,
                    actor=args.agent_id,
                    agent_id=args.agent_id,
                    run_id=args.run_id,
                    causation_id=registered.event_id,
                    payload=session.model_dump(mode="json"),
                )
            )
        events = [registered]
        if started is not None:
            events.append(started)
        _emit(
            {"ok": True, "identity": identity, "session": session, "events": events},
            as_json=_as_json(args),
        )
        return EXIT_OK
    finally:
        directory.close()


def _handle_wait(args: argparse.Namespace) -> int:
    from .agents import AgentDirectory, AgentDirectoryError
    from .inbox import wait
    from .models import AgentRuntimeState

    _best_effort_session_state(args.db, args.agent, AgentRuntimeState.WAITING_ON_BUS, "wait command started")
    result = wait(args.agent, args.timeout, db_path=args.db, busy=args.busy)
    if result.noop:
        _best_effort_session_state(args.db, args.agent, AgentRuntimeState.WAIT_RETURNED_NOOP, "wait returned noop")
    else:
        _best_effort_session_state(args.db, args.agent, AgentRuntimeState.DELIVERED_NOT_ACKED, "wait delivered item")
    try:
        directory = AgentDirectory(db_path=args.db)
        active_session = directory.get_active_session(args.agent)
    except AgentDirectoryError:
        active_session = None
    finally:
        if "directory" in locals():
            directory.close()
    _emit(
        {
            "ok": True,
            "kind": result.kind,
            "noop": result.noop,
            "timed_out": result.timed_out,
            "item": result.item,
            "session": active_session,
        },
        as_json=_as_json(args),
    )
    return EXIT_OK


def _handle_ack(args: argparse.Namespace) -> int:
    from .inbox import ack

    ok = ack(args.inbox_id, agent_id=args.agent, db_path=args.db)
    if not ok:
        raise CliError(
            f"inbox item not found or already acked: {args.inbox_id}",
            payload={"inbox_id": args.inbox_id, "agent_id": args.agent},
        )
    _emit({"ok": True, "inbox_id": args.inbox_id, "acked": True}, as_json=_as_json(args))
    return EXIT_OK


def _handle_worker_inbox_wait(args: argparse.Namespace) -> int:
    from .inbox import wait

    try:
        result = wait(
            args.agent,
            args.timeout,
            db_path=args.db,
            busy=args.busy,
            session_id=args.session_id,
            session_epoch=args.session_epoch,
            fencing_token=args.fencing_token,
            require_fence=True,
        )
    except PermissionError as exc:
        raise CliError(str(exc), payload={"agent_id": args.agent, "session_id": args.session_id}) from exc
    _emit(
        {
            "ok": True,
            "kind": result.kind,
            "noop": result.noop,
            "timed_out": result.timed_out,
            "item": result.item,
        },
        as_json=_as_json(args),
    )
    return EXIT_OK


def _handle_worker_inbox_ack(args: argparse.Namespace) -> int:
    from .inbox import ack

    try:
        ok = ack(
            args.inbox_id,
            agent_id=args.agent,
            db_path=args.db,
            session_id=args.session_id,
            session_epoch=args.session_epoch,
            fencing_token=args.fencing_token,
            require_fence=True,
        )
    except PermissionError as exc:
        raise CliError(str(exc), payload={"inbox_id": args.inbox_id, "agent_id": args.agent}) from exc
    if not ok:
        raise CliError(
            f"inbox item not found or fencing rejected: {args.inbox_id}",
            payload={"inbox_id": args.inbox_id, "agent_id": args.agent},
        )
    _emit({"ok": True, "inbox_id": args.inbox_id, "acked": True}, as_json=_as_json(args))
    return EXIT_OK


def _handle_context_get(args: argparse.Namespace) -> int:
    from .context import ContextPacketInvalidated, ContextStore

    store = ContextStore(args.db)
    try:
        packet = store.get_packet(args.packet_id, include_inactive=args.include_inactive)
    except ContextPacketInvalidated as exc:
        raise CliError(str(exc), code=EXIT_CONTEXT_INVALIDATED, payload=exc.to_payload()) from exc
    finally:
        store.close()
    _emit({"ok": True, "packet": packet}, as_json=_as_json(args))
    return EXIT_OK


def _handle_task_create(args: argparse.Namespace) -> int:
    from .authority import controller_principal
    from .tasks import TaskBoard

    board = TaskBoard(db_path=args.db, principal=controller_principal("cli-controller"))
    try:
        run = None
        run_id = args.run_id
        if args.run_title:
            run = board.create_run(args.run_title, objective=args.objective, created_by=args.owner)
            run_id = run.run_id
        task = board.create_task(
            args.title,
            run_id=run_id,
            owner_agent_id=args.owner,
            assignee_agent_id=args.assignee,
            priority=args.priority,
            parent_task_id=args.parent_task_id,
        )
        _emit({"ok": True, "run": run, "task": task}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        board.close()


def _handle_task_ack(args: argparse.Namespace) -> int:
    from .authority import controller_principal
    from .tasks import TaskBoard

    board = TaskBoard(db_path=args.db, principal=controller_principal("cli-controller"))
    try:
        task = board.acknowledge_task(args.task_id, actor=args.actor)
        _emit({"ok": True, "task": task}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        board.close()


def _handle_task_progress(args: argparse.Namespace) -> int:
    from .authority import controller_principal
    from .tasks import TaskBoard

    board = TaskBoard(db_path=args.db, principal=controller_principal("cli-controller"))
    try:
        task = board.start_task(args.task_id, actor=args.actor)
        _emit({"ok": True, "task": task}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        board.close()


def _handle_task_complete(args: argparse.Namespace) -> int:
    payload = _task_completion_claim_payload(args.db, args.task_id, actor=args.actor)
    payload["deprecated_adapter"] = _record_deprecated_adapter_use(
        args.db,
        path="cli.task.complete",
        replacement="cli.worker.task.complete",
        actor=args.actor,
    )
    _emit(payload, as_json=_as_json(args))
    return EXIT_OK


def _handle_worker_task_complete(args: argparse.Namespace) -> int:
    _assert_cli_worker_actor(args.actor)
    _emit(
        _task_completion_claim_payload(
            args.db,
            args.task_id,
            actor=args.actor,
            session_id=args.session_id,
            session_epoch=args.session_epoch,
            context_packet_id=args.context_packet_id,
        ),
        as_json=_as_json(args),
    )
    return EXIT_OK


def _handle_controller_task_claim_commit(args: argparse.Namespace) -> int:
    from .authority import controller_principal
    from .tasks import TaskBoard

    principal = controller_principal("cli-controller")
    board = TaskBoard(db_path=args.db, principal=principal)
    try:
        task = board.commit_task_claim(args.claim_id, actor="controller", principal=principal)
        _emit({"ok": True, "task": task, "claim": _task_claim_snapshot(args.db, args.claim_id)}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        board.close()


def _handle_task_fail(args: argparse.Namespace) -> int:
    from .tasks import TaskBoard

    board = TaskBoard(db_path=args.db)
    try:
        task = board.fail_task(args.task_id, args.reason, actor=args.actor)
        _emit({"ok": True, "task": task}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        board.close()


def _handle_review_request(args: argparse.Namespace) -> int:
    from .authority import controller_principal
    from .inbox import InboxStore

    inbox = InboxStore(args.db, principal=controller_principal("cli-controller"))
    try:
        payload = {
            "task_id": args.task_id,
            "run_id": args.run_id,
            "requester": args.requester,
            "worker": args.worker,
            "note": args.note,
        }
        item = inbox.enqueue(
            args.reviewer,
            "review_requested",
            payload,
            priority=args.priority,
            context_packet_id=args.context_packet_id,
            dedupe_key=f"review_requested:{args.task_id}:{args.reviewer}",
            actor=args.requester,
        )
        _emit({"ok": True, "item": item}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        inbox.close()


def _handle_review_submit(args: argparse.Namespace) -> int:
    from .reviews import ReviewBoard

    findings = _build_findings(args)
    board = ReviewBoard(db_path=args.db)
    try:
        created = board.request_changes(
            run_id=args.run_id,
            task_id=args.task_id,
            worker_agent_id=args.worker,
            reviewer_agent_id=args.reviewer,
            findings=findings,
        )
        _emit({"ok": True, "findings": created}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        board.close()


def _handle_review_resolve(args: argparse.Namespace) -> int:
    from .reviews import ReviewBoard

    board = ReviewBoard(db_path=args.db)
    try:
        finding = board.resolve_finding(args.finding_id, resolved_by=args.resolved_by, status=args.status)
        _emit({"ok": True, "finding": finding}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        board.close()


def _handle_gate_create(args: argparse.Namespace) -> int:
    from .authority import controller_principal
    from .gates import GateBoard

    gates = GateBoard(db_path=args.db, principal=controller_principal("cli-controller"))
    try:
        gate = gates.create_gate(
            args.name,
            run_id=args.run_id,
            task_id=args.task_id,
            owner_agent_id=args.owner,
            requested_by=args.requested_by,
            risk=args.risk,
            gate_kind=args.gate_kind,
            checklist=args.checklist,
            required_evidence=args.required_evidence,
        )
        output: dict[str, Any] = {"ok": True, "gate": gate}
        deprecated = _deprecated_adapter_from_args(args)
        if deprecated is not None:
            output["deprecated_adapter"] = deprecated
        _emit(output, as_json=_as_json(args))
        return EXIT_OK
    finally:
        gates.close()


def _handle_gate_approve(args: argparse.Namespace) -> int:
    from .gates import GateBoard

    principal = _control_principal_for_actor(args.actor, source="cli")
    gates = GateBoard(db_path=args.db, principal=principal)
    try:
        gate = gates.approve_gate(
            args.gate_id,
            actor=args.actor,
            reason=args.reason,
            allow_high_risk=args.allow_high_risk,
            action_agent_id=args.action_agent,
            evidence_artifact_ids=args.evidence_artifact_id,
            principal=principal,
        )
        _emit({"ok": True, "gate": gate}, as_json=_as_json(args))
        return EXIT_OK
    except PermissionError as exc:
        raise CliError(
            str(exc),
            payload=_protocol_reject_payload(args.db, action="gate.approved"),
        ) from exc
    except sqlite3.IntegrityError as exc:
        if "ProtocolKernel UnitOfWork" not in str(exc):
            raise
        raise CliError(
            "direct gate approval requires ProtocolKernel UnitOfWork",
            payload={
                "error": "protocol_guard",
                "gate_id": args.gate_id,
                "projection_effect": "REJECT",
            },
        ) from exc
    finally:
        gates.close()


def _handle_gate_reject(args: argparse.Namespace) -> int:
    from .gates import GateBoard

    principal = _control_principal_for_actor(args.actor, source="cli")
    gates = GateBoard(db_path=args.db, principal=principal)
    try:
        gate = gates.reject_gate(args.gate_id, actor=args.actor, reason=args.reason, principal=principal)
        output: dict[str, Any] = {"ok": True, "gate": gate}
        deprecated = _deprecated_adapter_from_args(args)
        if deprecated is not None:
            output["deprecated_adapter"] = deprecated
        _emit(output, as_json=_as_json(args))
        return EXIT_OK
    except PermissionError as exc:
        raise CliError(
            str(exc),
            payload=_protocol_reject_payload(args.db, action="gate.rejected"),
        ) from exc
    finally:
        gates.close()


def _handle_gate_escalate(args: argparse.Namespace) -> int:
    from .gates import GateBoard

    principal = _control_principal_for_actor(args.actor, source="cli")
    gates = GateBoard(db_path=args.db, principal=principal)
    try:
        gate = gates.escalate_gate(args.gate_id, actor=args.actor, reason=args.reason, principal=principal)
        output: dict[str, Any] = {"ok": True, "gate": gate}
        deprecated = _deprecated_adapter_from_args(args)
        if deprecated is not None:
            output["deprecated_adapter"] = deprecated
        _emit(output, as_json=_as_json(args))
        return EXIT_OK
    except PermissionError as exc:
        raise CliError(
            str(exc),
            payload=_protocol_reject_payload(args.db, action="gate.escalated"),
        ) from exc
    finally:
        gates.close()


def _handle_interrupt_create(args: argparse.Namespace) -> int:
    from .authority import user_principal
    from .context import ContextStore
    from .inbox import InboxStore
    from .router import InterruptRoutingTarget, create_user_interrupt

    principal = user_principal("cli-user")
    context = ContextStore(args.db, principal=principal)
    inbox = InboxStore(args.db, principal=principal)
    try:
        target = InterruptRoutingTarget(
            controller=args.controller,
            observer=args.observer,
            task_owner=args.task_owner,
            task_assignee=args.task_assignee,
            helper_agents=args.helper_agent,
            qa_agent=args.qa_agent,
            gate_owner=args.gate_owner,
            downstream_task_owners=args.downstream_owner,
            additional_agents=args.agent,
        )
        result = create_user_interrupt(
            actor=args.actor,
            target=target,
            text=args.text,
            run_id=args.run_id,
            task_id=args.task_id,
            payload=_parse_json_object(args.payload_json, "--payload-json"),
            db_path=args.db,
            inbox_store=inbox,
            context_store=context,
        )
        output: dict[str, Any] = {"ok": True, "result": result}
        deprecated = _deprecated_adapter_from_args(args)
        if deprecated is not None:
            output["deprecated_adapter"] = deprecated
        _emit(output, as_json=_as_json(args))
        return EXIT_OK
    finally:
        inbox.close()
        context.close()


def _handle_replacement_approve(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from .agents import AgentDirectory
    from .authority import controller_principal
    from .context import ContextStore
    from .inbox import InboxStore
    from .replacement import ReplacementCoordinator, ReplacementRecommendation, ReplacementTrigger
    from .models import new_id
    from .store import EventStore

    directory = AgentDirectory(db_path=args.db)
    principal = controller_principal("cli-controller")
    context = ContextStore(args.db, principal=principal)
    inbox = InboxStore(args.db, principal=principal)
    coordinator = ReplacementCoordinator(
        directory=directory,
        context_sink=context,
        inbox=inbox,
        event_store=EventStore(args.db),
        db_path=args.db,
    )
    try:
        old_session = directory.get_session(args.old_session_id)
        required_capabilities = tuple(args.required_capability)
        recommendation = coordinator.recommend_for_session(
            args.old_session_id,
            task_id=args.task_id,
            run_id=args.run_id or old_session.run_id,
            required_capabilities=required_capabilities,
            role=args.role,
        )
        selected_candidate = _select_replacement_candidate(
            coordinator,
            old_session=old_session,
            required_capabilities=required_capabilities,
            role=args.role,
            candidate_agent=args.candidate_agent,
            candidate_session_id=args.candidate_session_id,
        )
        if selected_candidate is not None:
            if recommendation is None:
                recommendation = ReplacementRecommendation(
                    recommendation_id=new_id("replrec"),
                    task_id=args.task_id,
                    run_id=args.run_id or old_session.run_id,
                    old_session_id=old_session.session_id,
                    old_agent_id=old_session.agent_id,
                    candidate=selected_candidate,
                    triggers=(ReplacementTrigger("manual_cli_approval", "manual replacement approval", 1.0),),
                    required_capabilities=required_capabilities,
                    role=args.role,
                )
            else:
                recommendation = replace(recommendation, candidate=selected_candidate)
        if recommendation is None:
            raise CliError(
                f"no replacement recommendation for session: {args.old_session_id}",
                payload={"old_session_id": args.old_session_id, "task_id": args.task_id},
            )
        approval = coordinator.approve(
            recommendation,
            approved_by=args.approved_by,
            next_action=args.next_action,
            required_artifacts=tuple(args.artifact),
            invalidated_packet_ids=tuple(args.invalidated_packet_id),
        )
        _emit(
            {
                "ok": True,
                "recommendation": recommendation,
                "approval": approval,
                "context_packet_id": approval.context_packet.packet_id,
                "invalidated_packet_ids": _context_invalidated_packet_ids(approval.context_packet),
                "event_chain": _replacement_event_chain(args.db, recommendation.recommendation_id),
            },
            as_json=_as_json(args),
        )
        return EXIT_OK
    finally:
        inbox.close()
        context.close()
        directory.close()


def _handle_artifact_create(args: argparse.Namespace) -> int:
    from .authority import controller_principal
    from .tasks import TaskBoard

    board = TaskBoard(db_path=args.db, principal=controller_principal("cli-controller"))
    try:
        artifact = board.create_artifact(
            args.kind,
            args.uri,
            run_id=args.run_id,
            task_id=args.task_id,
            metadata=_parse_json_object(args.metadata_json, "--metadata-json"),
            created_by=args.created_by,
        )
        _emit({"ok": True, "artifact": artifact}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        board.close()


def _handle_models(args: argparse.Namespace) -> int:
    from . import models

    model_names = [
        "BusEvent",
        "EventType",
        "AgentIdentity",
        "AgentSession",
        "AgentRuntimeState",
        "AgentHealth",
        "AgentCapability",
        "InboxItem",
        "ContextPacket",
        "TaskRecord",
        "GateRecord",
        "ReviewFinding",
        "ArtifactRecord",
    ]
    available = [name for name in model_names if hasattr(models, name)]
    if _as_json(args):
        _emit({"ok": True, "models": available}, as_json=True)
    else:
        print("\n".join(available))
    return EXIT_OK


def _handle_protocol_events(args: argparse.Namespace) -> int:
    from .store import EventStore

    events = EventStore(args.db).query_events(event_type=args.type, limit=args.limit)
    _emit({"ok": True, "events": events}, as_json=_as_json(args))
    return EXIT_OK


def _best_effort_session_state(db_path: str | os.PathLike[str] | None, agent_id: str, state: Any, reason: str) -> None:
    from .agents import AgentDirectory, AgentDirectoryError

    directory = AgentDirectory(db_path=db_path)
    try:
        session = directory.get_active_session(agent_id)
        if session is not None:
            directory.update_session_state(session.session_id, state, reason=reason)
    except AgentDirectoryError:
        return
    finally:
        directory.close()


def _select_replacement_candidate(
    coordinator: Any,
    *,
    old_session: Any,
    required_capabilities: tuple[str, ...],
    role: str | None,
    candidate_agent: str | None,
    candidate_session_id: str | None,
) -> Any | None:
    if candidate_agent is None and candidate_session_id is None:
        return None
    candidates = coordinator.score_candidates(
        old_session=old_session,
        required_capabilities=required_capabilities,
        role=role,
    )
    for candidate in candidates:
        if candidate_session_id is not None and candidate.session_id == candidate_session_id:
            return candidate
        if candidate_agent is not None and candidate.agent_id == candidate_agent:
            return candidate
    raise CliError(
        "requested replacement candidate is not eligible",
        payload={"candidate_agent": candidate_agent, "candidate_session_id": candidate_session_id},
    )


def _task_completion_claim_payload(
    db_path: str | os.PathLike[str] | None,
    task_id: str,
    *,
    actor: str | None,
    session_id: str | None = None,
    session_epoch: int | None = None,
    context_packet_id: str | None = None,
) -> dict[str, Any]:
    from .protocol import ProtocolKernel
    from .tasks import TaskBoard

    result = ProtocolKernel(db_path).record_task_completion_claim(
        task_id,
        actor=actor,
        agent_id=actor,
        session_id=session_id,
        session_epoch=session_epoch,
        context_packet_id=context_packet_id,
    )
    board = TaskBoard(db_path=db_path)
    try:
        task = board.get_task(task_id)
    finally:
        board.close()
    return {
        "ok": True,
        "task": task,
        "claim": _task_claim_snapshot(db_path, result.claim_id),
        "event_id": result.event_id,
        "projection_effect": result.projection_effect,
        "fencing_result": result.fencing_result,
    }


def _task_claim_snapshot(db_path: str | os.PathLike[str] | None, claim_id: str | None) -> dict[str, Any]:
    if not claim_id:
        return {}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("select * from task_claims where claim_id = ?", (claim_id,)).fetchone()
    if row is None:
        return {}
    return {
        "claim_id": row["claim_id"],
        "claim_kind": row["claim_kind"],
        "status": row["status"],
        "task_id": row["task_id"],
        "run_id": row["run_id"],
        "agent_id": row["agent_id"],
        "session_id": row["session_id"],
        "session_epoch": row["session_epoch"],
        "context_packet_id": row["context_packet_id"],
        "created_from_event_id": row["created_from_event_id"],
        "committed_by_event_id": row["committed_by_event_id"],
        "payload": json.loads(row["payload_json"] or "{}"),
    }


def _assert_cli_worker_actor(actor: str | None) -> None:
    normalized = (actor or "").strip().lower()
    if not normalized or normalized in {"controller", "user"}:
        raise CliError(
            "worker actor is required for worker CLI writes",
            payload={"error": "authority_reject", "actor": actor, "projection_effect": "REJECT"},
        )


def _deprecated_adapter_from_args(args: argparse.Namespace) -> dict[str, Any] | None:
    path = getattr(args, "deprecated_adapter_path", None)
    replacement = getattr(args, "deprecated_adapter_replacement", None)
    if path is None or replacement is None:
        return None
    return _record_deprecated_adapter_use(
        args.db,
        path=path,
        replacement=replacement,
        actor=getattr(args, "actor", None),
        explicit_compatibility_mode=bool(getattr(args, "as_controller", False)),
    )


def _record_deprecated_adapter_use(
    db_path: str | os.PathLike[str] | None,
    *,
    path: str,
    replacement: str,
    actor: str | None,
    explicit_compatibility_mode: bool = False,
) -> dict[str, Any]:
    from .models import BusEvent, EventType
    from .protocol_models import FencingResult, ProjectionEffect
    from .store import EventStore

    event = EventStore(db_path).append_event(
        BusEvent(
            type=EventType.ADAPTER_DEPRECATED_PATH_USED,
            actor=actor,
            actor_role="adapter",
            projection_effect=ProjectionEffect.AUDIT_ONLY,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload={
                "path": path,
                "replacement": replacement,
                "explicit_compatibility_mode": explicit_compatibility_mode,
            },
        )
    )
    return event.model_dump(mode="json")


def _control_principal_for_actor(actor: str, *, source: str) -> Any:
    from .authority import controller_principal, user_principal

    normalized = actor.strip().lower()
    if normalized == "controller":
        return controller_principal(f"{source}-controller")
    if normalized == "user":
        return user_principal(f"{source}-user")
    raise CliError(
        f"unsupported gate decision actor '{actor}'; expected controller or user",
        payload={"error": "authority_reject", "actor": actor, "projection_effect": "REJECT"},
    )


def _protocol_reject_payload(db_path: str | os.PathLike[str] | None, *, action: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": "protocol_reject", "projection_effect": "REJECT"}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            select violation_id, projection_effect, fencing_result
              from protocol_violations
             where action = ?
             order by created_at desc
             limit 1
            """,
            (action,),
        ).fetchone()
    if row is not None:
        payload.update(
            {
                "violation_id": row["violation_id"],
                "projection_effect": row["projection_effect"],
                "fencing_result": row["fencing_result"],
            }
        )
    return payload


def _context_invalidated_packet_ids(packet: Any) -> list[str]:
    instructions = getattr(packet, "instructions", None)
    if isinstance(instructions, dict):
        values = instructions.get("invalidated_packet_ids", [])
        if isinstance(values, list):
            return [str(value) for value in values]
    return []


def _replacement_event_chain(db_path: str | os.PathLike[str] | None, recommendation_id: str) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            select event_id, type, causation_id, correlation_id, projection_effect, fencing_result, payload_json
              from event_log
             where correlation_id = ?
             order by seq asc
            """,
            (recommendation_id,),
        ).fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        events.append(
            {
                "event_id": row["event_id"],
                "type": row["type"],
                "causation_id": row["causation_id"],
                "correlation_id": row["correlation_id"],
                "projection_effect": row["projection_effect"],
                "fencing_result": row["fencing_result"],
                "payload": json.loads(row["payload_json"] or "{}"),
            }
        )
    return events


def _ensure_operational_schema(db_path: str | os.PathLike[str] | None, *, reset: bool = False) -> Path:
    from .agents import AgentDirectory
    from .context import ContextStore
    from .db import initialize_database
    from .gates import GateBoard
    from .inbox import InboxStore
    from .reviews import ReviewBoard
    from .tasks import TaskBoard

    path = initialize_database(db_path, reset=reset)
    resources = [
        InboxStore(path),
        AgentDirectory(db_path=path),
        ContextStore(path),
        TaskBoard(db_path=path),
        GateBoard(db_path=path),
        ReviewBoard(db_path=path),
    ]
    for resource in resources:
        close = getattr(resource, "close", None)
        if callable(close):
            close()
    return path


def _build_findings(args: argparse.Namespace) -> list[dict[str, Any]]:
    findings = [_parse_json_object(raw, "--finding-json") for raw in args.finding_json]
    if findings:
        return findings
    missing = [
        name
        for name, value in (
            ("--severity", args.severity),
            ("--category", args.category),
            ("--evidence", args.evidence),
            ("--requested-change", args.requested_change),
        )
        if not value
    ]
    if missing:
        raise CliUsageError(f"review submit requires --finding-json or {', '.join(missing)}")
    return [
        {
            "severity": args.severity,
            "category": args.category,
            "file_path": args.file_path,
            "evidence": args.evidence,
            "requested_change": args.requested_change,
            "blocking": bool(args.blocking),
        }
    ]


def _parse_json_object(raw: str | None, option_name: str) -> dict[str, Any]:
    if raw in (None, ""):
        return {}
    raw = _read_json_argument(raw, option_name)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliUsageError(f"{option_name} must be valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise CliUsageError(f"{option_name} must be a JSON object")
    return value


def _read_json_argument(raw: str, option_name: str) -> str:
    if not raw.startswith("@"):
        return raw
    path_text = raw[1:]
    if not path_text:
        raise CliUsageError(f"{option_name} @file reference requires a path")
    path = Path(path_text).expanduser()
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        detail = exc.strerror or str(exc)
        raise CliUsageError(f"{option_name} could not read JSON file {path}: {detail}") from exc


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: _to_jsonable(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (tuple, list)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    return value


def _emit(payload: dict[str, Any], *, as_json: bool) -> None:
    jsonable = _to_jsonable(payload)
    if as_json:
        print(json.dumps(jsonable, ensure_ascii=False, sort_keys=True), flush=True)
    else:
        print(_humanize(jsonable), flush=True)


def _emit_error(exc: CliError, *, as_json: bool) -> None:
    payload = {"ok": False, "error": exc.payload.get("error", "cli_error"), "message": str(exc), **exc.payload}
    if as_json:
        print(json.dumps(_to_jsonable(payload), ensure_ascii=False, sort_keys=True), file=sys.stderr, flush=True)
    else:
        print(f"error: {str(exc)}", file=sys.stderr, flush=True)


def _humanize(payload: dict[str, Any]) -> str:
    if "ok" in payload and len(payload) == 1:
        return "ok"
    if payload.get("ok") is True:
        pieces = ["ok"]
        for key, value in payload.items():
            if key == "ok" or value is None:
                continue
            if isinstance(value, dict):
                identifier = value.get(f"{key}_id") or value.get("id")
                if identifier:
                    pieces.append(f"{key}={identifier}")
            elif isinstance(value, list):
                pieces.append(f"{key}={len(value)}")
            else:
                pieces.append(f"{key}={value}")
        return " ".join(pieces)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _add_db(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", help="path to the SQLite database")


def _add_json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="print structured JSON output")


def _add_interrupt_create_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--actor", default="user")
    parser.add_argument("--text", default="")
    parser.add_argument("--run-id")
    parser.add_argument("--task-id")
    parser.add_argument("--controller", default="controller")
    parser.add_argument("--observer", default="observer")
    parser.add_argument("--task-owner")
    parser.add_argument("--task-assignee")
    parser.add_argument("--helper-agent", action="append", default=[])
    parser.add_argument("--qa-agent", default="qa")
    parser.add_argument("--gate-owner")
    parser.add_argument("--downstream-owner", action="append", default=[])
    parser.add_argument("--agent", action="append", default=[], help="additional affected agent")
    parser.add_argument("--payload-json", help="additional JSON object payload")
    _add_db(parser)
    _add_json(parser)


def _add_finding_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--finding-json", action="append", default=[], help="finding JSON object; repeatable")
    parser.add_argument("--severity")
    parser.add_argument("--category")
    parser.add_argument("--file-path")
    parser.add_argument("--evidence")
    parser.add_argument("--requested-change")
    parser.add_argument("--blocking", action="store_true")


def _as_json(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json", False))


def _argv_wants_json(argv: list[str]) -> bool:
    return "--json" in argv


if __name__ == "__main__":
    sys.exit(main())
