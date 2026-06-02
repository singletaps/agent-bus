from __future__ import annotations

import sqlite3

from agent_bus.agents import AgentDirectory
from agent_bus.authority import controller_principal
from agent_bus.context import ContextStore
from agent_bus.inbox import InboxStore
from agent_bus.protocol_models import BindingStatus, PacketKind
from agent_bus.tasks import TaskBoard


def test_task_assignment_creates_context_packet_binding_and_bound_inbox_item(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("worker.backend")
    directory.start_session("worker.backend", session_id="session-worker")
    board = TaskBoard(db_path=db_path, agent_directory=directory, principal=controller_principal())
    task = board.create_task("Bound assignment", run_id="run-1", owner_agent_id="controller")

    assigned = board.assign_task(task.task_id, "worker.backend", actor="controller")

    assert assigned.assignee_agent_id == "worker.backend"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        packet = conn.execute("select * from context_packets where task_id = ?", (task.task_id,)).fetchone()
        binding = conn.execute(
            "select * from task_context_bindings where task_id = ?",
            (task.task_id,),
        ).fetchone()
        inbox = conn.execute("select * from inbox_items where agent_id = 'worker.backend'").fetchone()

    assert packet["agent_id"] == "worker.backend"
    assert packet["packet_kind"] == PacketKind.ASSIGNMENT.value
    assert binding["context_packet_id"] == packet["packet_id"]
    assert binding["status"] == BindingStatus.ACTIVE.value
    assert binding["session_id"] == "session-worker"
    assert inbox["context_packet_id"] == packet["packet_id"]


def test_context_invalidation_and_supersession_update_bindings(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    store = ContextStore(db_path, principal=controller)
    packet = store.create_packet(
        agent_id="worker.backend",
        task_id="task-1",
        run_id="run-1",
        summary="first",
        actor="controller",
        session_id="session-worker",
        session_epoch=1,
    )

    replacement = store.supersede_packet(packet.packet_id, summary="second", actor="controller")

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        old_binding = conn.execute(
            "select * from task_context_bindings where context_packet_id = ?",
            (packet.packet_id,),
        ).fetchone()
        new_binding = conn.execute(
            "select * from task_context_bindings where context_packet_id = ?",
            (replacement.packet_id,),
        ).fetchone()

    assert old_binding["status"] == BindingStatus.SUPERSEDED.value
    assert new_binding["status"] == BindingStatus.ACTIVE.value

    store.invalidate_packet(replacement.packet_id, invalidated_by_event_id="evt-stop", actor="controller")
    with sqlite3.connect(db_path) as conn:
        status = conn.execute(
            "select status from task_context_bindings where context_packet_id = ?",
            (replacement.packet_id,),
        ).fetchone()[0]
    assert status == BindingStatus.INVALIDATED.value


def test_bound_inbox_delivery_and_ack_are_fenced_to_worker_session(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    context = ContextStore(db_path, principal=controller)
    packet = context.create_packet(agent_id="worker.backend", task_id="task-1", summary="do it")
    inbox = InboxStore(db_path, principal=controller)
    item = inbox.enqueue(
        "worker.backend",
        "task_assigned",
        {"task_id": "task-1"},
        context_packet_id=packet.packet_id,
        actor="controller",
    )
    from agent_bus.fencing import FencingService

    fence = FencingService(db_path).register_session(
        "session-worker",
        agent_id="worker.backend",
        token="worker-token",
    )

    delivered = inbox.wait(
        "worker.backend",
        timeout=0.01,
        session_id=fence.session_id,
        session_epoch=fence.session_epoch,
        fencing_token=fence.raw_token,
    ).item

    assert delivered is not None
    assert delivered.delivered_to_session_id == fence.session_id
    assert inbox.ack(
        item.inbox_id,
        agent_id="worker.backend",
        session_id=fence.session_id,
        session_epoch=fence.session_epoch,
        fencing_token=fence.raw_token,
    )
    assert inbox.get(item.inbox_id).acked_by_session_id == fence.session_id


def test_inbox_ack_rejects_wrong_fenced_session(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    inbox = InboxStore(db_path, principal=controller)
    item = inbox.enqueue("worker.backend", "task_assigned", {"task_id": "task-1"}, actor="controller")
    from agent_bus.fencing import FencingService

    good = FencingService(db_path).register_session("good-session", agent_id="worker.backend", token="good")
    wrong = FencingService(db_path).register_session("wrong-session", agent_id="worker.other", token="wrong")
    assert inbox.wait(
        "worker.backend",
        timeout=0.01,
        session_id=good.session_id,
        session_epoch=good.session_epoch,
        fencing_token=good.raw_token,
    ).item is not None

    assert (
        inbox.ack(
            item.inbox_id,
            agent_id="worker.backend",
            session_id=wrong.session_id,
            session_epoch=wrong.session_epoch,
            fencing_token=wrong.raw_token,
        )
        is False
    )
    assert inbox.get(item.inbox_id).acked_at is None
