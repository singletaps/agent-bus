from __future__ import annotations

import argparse
import dataclasses
import json
import os
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
    _add_db(gate_create)
    _add_json(gate_create)
    for command_name in ("approve", "reject", "escalate"):
        gate_action = gate_subparsers.add_parser(command_name, help=f"{command_name} a gate")
        gate_action.add_argument("gate_id")
        gate_action.add_argument("--actor", default="controller")
        gate_action.add_argument("--reason")
        if command_name == "approve":
            gate_action.add_argument("--allow-high-risk", action="store_true")
            gate_action.add_argument("--action-agent", default="controller")
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
    interrupt_create.add_argument("--actor", default="user")
    interrupt_create.add_argument("--text", default="")
    interrupt_create.add_argument("--run-id")
    interrupt_create.add_argument("--task-id")
    interrupt_create.add_argument("--controller", default="controller")
    interrupt_create.add_argument("--observer", default="observer")
    interrupt_create.add_argument("--task-owner")
    interrupt_create.add_argument("--task-assignee")
    interrupt_create.add_argument("--helper-agent", action="append", default=[])
    interrupt_create.add_argument("--qa-agent", default="qa")
    interrupt_create.add_argument("--gate-owner")
    interrupt_create.add_argument("--downstream-owner", action="append", default=[])
    interrupt_create.add_argument("--agent", action="append", default=[], help="additional affected agent")
    interrupt_create.add_argument("--payload-json", help="additional JSON object payload")
    _add_db(interrupt_create)
    _add_json(interrupt_create)

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
    from .context import ContextStore
    from .gates import GateBoard
    from .inbox import InboxStore
    from .tasks import TaskBoard

    directory = AgentDirectory(db_path=db_path)
    board = TaskBoard(db_path=db_path, agent_directory=directory)
    context = ContextStore(db_path)
    inbox = InboxStore(db_path)
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
    from .tasks import TaskBoard

    board = TaskBoard(db_path=args.db)
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
    from .tasks import TaskBoard

    board = TaskBoard(db_path=args.db)
    try:
        task = board.acknowledge_task(args.task_id, actor=args.actor)
        _emit({"ok": True, "task": task}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        board.close()


def _handle_task_progress(args: argparse.Namespace) -> int:
    from .tasks import TaskBoard

    board = TaskBoard(db_path=args.db)
    try:
        task = board.start_task(args.task_id, actor=args.actor)
        _emit({"ok": True, "task": task}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        board.close()


def _handle_task_complete(args: argparse.Namespace) -> int:
    from .tasks import TaskBoard

    board = TaskBoard(db_path=args.db)
    try:
        task = board.complete_task(args.task_id, actor=args.actor)
        _emit({"ok": True, "task": task}, as_json=_as_json(args))
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
    from .inbox import InboxStore

    inbox = InboxStore(args.db)
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
    from .gates import GateBoard

    gates = GateBoard(db_path=args.db)
    try:
        gate = gates.create_gate(
            args.name,
            run_id=args.run_id,
            task_id=args.task_id,
            owner_agent_id=args.owner,
            requested_by=args.requested_by,
            risk=args.risk,
        )
        _emit({"ok": True, "gate": gate}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        gates.close()


def _handle_gate_approve(args: argparse.Namespace) -> int:
    from .gates import GateBoard

    gates = GateBoard(db_path=args.db)
    try:
        gate = gates.approve_gate(
            args.gate_id,
            actor=args.actor,
            reason=args.reason,
            allow_high_risk=args.allow_high_risk,
            action_agent_id=args.action_agent,
        )
        _emit({"ok": True, "gate": gate}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        gates.close()


def _handle_gate_reject(args: argparse.Namespace) -> int:
    from .gates import GateBoard

    gates = GateBoard(db_path=args.db)
    try:
        gate = gates.reject_gate(args.gate_id, actor=args.actor, reason=args.reason)
        _emit({"ok": True, "gate": gate}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        gates.close()


def _handle_gate_escalate(args: argparse.Namespace) -> int:
    from .gates import GateBoard

    gates = GateBoard(db_path=args.db)
    try:
        gate = gates.escalate_gate(args.gate_id, actor=args.actor, reason=args.reason)
        _emit({"ok": True, "gate": gate}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        gates.close()


def _handle_interrupt_create(args: argparse.Namespace) -> int:
    from .context import ContextStore
    from .inbox import InboxStore
    from .router import InterruptRoutingTarget, create_user_interrupt

    context = ContextStore(args.db)
    inbox = InboxStore(args.db)
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
        _emit({"ok": True, "result": result}, as_json=_as_json(args))
        return EXIT_OK
    finally:
        inbox.close()
        context.close()


def _handle_replacement_approve(args: argparse.Namespace) -> int:
    from dataclasses import replace

    from .agents import AgentDirectory
    from .context import ContextStore
    from .inbox import InboxStore
    from .replacement import ReplacementCoordinator, ReplacementRecommendation, ReplacementTrigger
    from .models import new_id
    from .store import EventStore

    directory = AgentDirectory(db_path=args.db)
    context = ContextStore(args.db)
    inbox = InboxStore(args.db)
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
            {"ok": True, "recommendation": recommendation, "approval": approval},
            as_json=_as_json(args),
        )
        return EXIT_OK
    finally:
        inbox.close()
        context.close()
        directory.close()


def _handle_artifact_create(args: argparse.Namespace) -> int:
    from .tasks import TaskBoard

    board = TaskBoard(db_path=args.db)
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
