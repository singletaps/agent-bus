from __future__ import annotations

import sqlite3

import pytest

from agent_bus.context import (
    ACTIVE,
    INVALIDATED,
    SUPERSEDED,
    ContextPacketInvalidated,
    ContextStore,
)
from agent_bus.inbox import InboxStore
from agent_bus.router import InterruptRoutingTarget, create_user_interrupt
from agent_bus.store import EventStore


def test_migrate_creates_context_packets_table(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    store = ContextStore(db_path)
    store.close()

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("pragma table_info(context_packets)").fetchall()}

    assert {
        "packet_id",
        "version",
        "agent_id",
        "task_id",
        "run_id",
        "status",
        "summary",
        "instructions_json",
        "artifact_refs_json",
        "created_from_event_id",
        "supersedes_packet_id",
        "superseded_by_packet_id",
        "invalidated_by_event_id",
        "created_at",
        "invalidated_at",
    } <= columns


def test_create_and_get_packet_round_trips_structured_context(tmp_path):
    store = ContextStore(tmp_path / "agent-bus.sqlite3")

    packet = store.create_packet(
        agent_id="runtime-worker-1",
        task_id="task-b1",
        run_id="run-1",
        summary="Build context packets",
        instructions={"next": "implement tests", "constraints": ["minimal actionable context"]},
        artifact_refs=["README.md"],
        created_from_event_id="evt-source",
        actor="runtime-worker-1",
    )
    loaded = store.get_packet(packet.packet_id)
    events = EventStore(store.db_path).query_events(event_type="context.created")

    assert loaded == packet
    assert loaded.status == ACTIVE
    assert loaded.instructions["constraints"] == ["minimal actionable context"]
    assert loaded.artifact_refs == ["README.md"]
    assert events[0].payload["packet_id"] == packet.packet_id


def test_invalidate_packet_returns_structured_invalidated_error(tmp_path):
    store = ContextStore(tmp_path / "agent-bus.sqlite3")
    packet = store.create_packet(agent_id="worker", summary="old context")

    invalidated = store.invalidate_packet(
        packet.packet_id,
        invalidated_by_event_id="evt-interrupt",
        actor="user",
    )

    assert invalidated.status == INVALIDATED
    assert invalidated.invalidated_by_event_id == "evt-interrupt"
    with pytest.raises(ContextPacketInvalidated) as exc_info:
        store.get_packet(packet.packet_id)
    assert exc_info.value.to_payload() == {
        "error": "context_packet_invalidated",
        "packet_id": packet.packet_id,
        "invalidated_by_event_id": "evt-interrupt",
        "invalidated_at": invalidated.invalidated_at,
        "superseded_by_packet_id": None,
    }


def test_supersede_packet_links_old_and_replacement(tmp_path):
    store = ContextStore(tmp_path / "agent-bus.sqlite3")
    old = store.create_packet(
        agent_id="worker",
        task_id="task-1",
        run_id="run-1",
        summary="old",
        instructions=["do old thing"],
    )

    replacement = store.supersede_packet(
        old.packet_id,
        summary="new",
        instructions=["do new thing"],
        created_from_event_id="evt-replan",
    )
    old_after = store.get_packet(old.packet_id, include_inactive=True)

    assert replacement.version == old.version + 1
    assert replacement.supersedes_packet_id == old.packet_id
    assert replacement.task_id == old.task_id
    assert old_after.status == SUPERSEDED
    assert old_after.superseded_by_packet_id == replacement.packet_id


def test_rehydration_packet_contains_required_actionable_fields(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    inbox = InboxStore(db_path=db_path)
    item = inbox.enqueue("replacement-worker", "task_assigned", {"task_id": "task-1"})
    inbox.close()

    store = ContextStore(db_path)
    packet = store.create_rehydration_packet(
        agent_id="replacement-worker",
        task_id="task-1",
        run_id="run-1",
        role_contract="Worker 1 owns context packets",
        current_task="Resume B1",
        last_known_summary="Context table created",
        required_artifacts=["agent_bus/context.py"],
        next_action="Run tests",
        invalidated_packet_ids=["ctx_old"],
        created_from_event_id="evt-rehydrate",
    )

    assert packet.instructions == {
        "kind": "rehydration",
        "role_contract": "Worker 1 owns context packets",
        "current_task": "Resume B1",
        "last_known_summary": "Context table created",
        "open_inbox_item_ids": [item.inbox_id],
        "required_artifacts": ["agent_bus/context.py"],
        "next_action": "Run tests",
        "invalidated_packet_ids": ["ctx_old"],
    }
    assert packet.artifact_refs == ["agent_bus/context.py"]


def test_wait_item_can_reference_context_packet(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    context = ContextStore(db_path)
    packet = context.create_packet(agent_id="worker", summary="Use this packet")
    inbox = InboxStore(db_path=db_path)

    item = inbox.enqueue(
        "worker",
        "task_assigned",
        {"task_id": "task-1"},
        context_packet_id=packet.packet_id,
    )
    delivered = inbox.wait("worker", timeout=0.01)

    assert item.context_packet_id == packet.packet_id
    assert delivered.item is not None
    assert delivered.item.context_packet_id == packet.packet_id
    assert context.get_packet(delivered.item.context_packet_id).summary == "Use this packet"


def test_list_active_packets_and_invalidate_agent_contexts_for_router_hooks(tmp_path):
    store = ContextStore(tmp_path / "agent-bus.sqlite3")
    first = store.create_packet(agent_id="worker", task_id="task-1", run_id="run-1", summary="first")
    second = store.create_packet(agent_id="worker", task_id="task-2", run_id="run-1", summary="second")
    store.create_packet(agent_id="other", task_id="task-1", run_id="run-1", summary="other")

    assert [packet.packet_id for packet in store.list_active_packets(agent_id="worker")] == [
        first.packet_id,
        second.packet_id,
    ]

    invalidated = store.invalidate_agent_contexts(
        "worker",
        task_id="task-1",
        invalidated_by_event_id="evt-interrupt",
        actor="router",
    )

    assert [packet.packet_id for packet in invalidated] == [first.packet_id]
    assert store.get_packet(first.packet_id, include_inactive=True).status == INVALIDATED
    assert [packet.packet_id for packet in store.list_active_packets(agent_id="worker")] == [second.packet_id]


def test_rehydration_packet_without_inbox_table_uses_empty_open_items(tmp_path):
    store = ContextStore(tmp_path / "agent-bus.sqlite3")

    packet = store.create_rehydration_packet(
        agent_id="worker",
        role_contract="context owner",
        current_task="recover",
        last_known_summary="none",
        next_action="continue",
    )

    assert packet.instructions["open_inbox_item_ids"] == []


def test_user_interrupt_invalidates_affected_context_packets_only(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    context = ContextStore(db_path)
    inbox = InboxStore(db_path)
    affected = context.create_packet(
        agent_id="worker.owner",
        task_id="task-1",
        run_id="run-1",
        summary="affected",
    )
    unaffected_task = context.create_packet(
        agent_id="worker.owner",
        task_id="task-2",
        run_id="run-1",
        summary="not this task",
    )
    unrelated = context.create_packet(
        agent_id="worker.unrelated",
        task_id="task-1",
        run_id="run-1",
        summary="unrelated",
    )

    result = create_user_interrupt(
        actor="user",
        target=InterruptRoutingTarget(task_owner="worker.owner", qa_agent="qa"),
        text="Replan task",
        run_id="run-1",
        task_id="task-1",
        db_path=db_path,
        inbox_store=inbox,
        context_store=context,
    )

    assert result.invalidated_packet_ids_by_agent["worker.owner"] == [affected.packet_id]
    assert context.get_packet(affected.packet_id, include_inactive=True).status == INVALIDATED
    assert context.get_packet(affected.packet_id, include_inactive=True).invalidated_by_event_id == result.event.event_id
    assert context.get_packet(unaffected_task.packet_id).status == ACTIVE
    assert context.get_packet(unrelated.packet_id).status == ACTIVE
    assert inbox.wait("worker.owner", timeout=0.1, busy=True).item.kind == "user_interrupt"
    assert inbox.list_items("worker.unrelated") == []
