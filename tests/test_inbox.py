from __future__ import annotations

import sqlite3
import threading
import time

from agent_bus.authority import controller_principal, user_principal
from agent_bus.inbox import ACKED, BUSY_AGENT_DELIVERABLE_KINDS, InboxStore, ack, enqueue, migrate, wait
from agent_bus.models import EventType
from agent_bus.router import InterruptRoutingTarget, compute_affected_agents, create_user_interrupt
from agent_bus.store import EventStore


def test_migrate_creates_inbox_items_table(tmp_path):
    conn = sqlite3.connect(tmp_path / "bus.sqlite3")

    migrate(conn)

    columns = {
        row[1]
        for row in conn.execute("pragma table_info(inbox_items)").fetchall()
    }
    assert {
        "inbox_id",
        "agent_id",
        "priority",
        "kind",
        "status",
        "payload_json",
        "context_packet_id",
        "dedupe_key",
        "visible_at",
        "delivered_at",
        "acked_at",
        "expires_at",
        "created_at",
    } <= columns


def test_wait_times_out_with_noop(tmp_path):
    store = InboxStore(tmp_path / "bus.sqlite3")

    result = store.wait("worker.frontend", timeout=0.02, poll_interval=0.005)

    assert result.noop is True
    assert result.timed_out is True
    assert result.kind == "noop"
    assert result.item is None


def test_module_helpers_enqueue_wait_and_ack(tmp_path):
    db_path = tmp_path / "bus.sqlite3"
    item = enqueue(
        "agent",
        "task_assigned",
        {"task_id": "task_1"},
        db_path=db_path,
        actor="controller",
        principal=controller_principal(),
    )

    result = wait("agent", timeout=0.1, db_path=db_path)

    assert result.item.inbox_id == item.inbox_id
    assert ack(item.inbox_id, agent_id="agent", db_path=db_path) is True


def test_wait_blocks_until_visible_item_arrives(tmp_path):
    db_path = tmp_path / "bus.sqlite3"
    store = InboxStore(db_path)

    def enqueue_later() -> None:
        other = InboxStore(db_path, principal=controller_principal())
        other.enqueue("worker.backend", "task_assigned", {"task_id": "task_1"}, actor="controller")
        other.close()

    timer = threading.Timer(0.03, enqueue_later)
    timer.start()
    result = store.wait("worker.backend", timeout=1, poll_interval=0.005)
    timer.join()

    assert result.noop is False
    assert result.item is not None
    assert result.item.kind == "task_assigned"
    assert result.item.payload == {"task_id": "task_1"}
    assert store.get(result.item.inbox_id).status == "delivered"


def test_highest_priority_item_wins(tmp_path):
    store = InboxStore(tmp_path / "bus.sqlite3", principal=controller_principal())
    low = store.enqueue("agent", "low", priority=1, actor="controller")
    high = store.enqueue("agent", "high", priority=50, actor="controller")

    result = store.wait("agent", timeout=0.1)

    assert result.item.inbox_id == high.inbox_id
    assert store.get(low.inbox_id).status == "queued"


def test_ack_marks_item_done_and_prevents_redelivery(tmp_path):
    store = InboxStore(tmp_path / "bus.sqlite3", principal=controller_principal())
    item = store.enqueue("agent", "task_assigned", actor="controller")
    delivered = store.wait("agent", timeout=0.1).item

    assert delivered.inbox_id == item.inbox_id
    assert store.ack(delivered.inbox_id, agent_id="agent") is True

    saved = store.get(item.inbox_id)
    assert saved.status == ACKED
    assert saved.acked_at is not None
    assert store.wait("agent", timeout=0.02, visibility_timeout=0.01).noop is True


def test_unacked_item_redelivers_after_visibility_timeout(tmp_path):
    store = InboxStore(tmp_path / "bus.sqlite3", principal=controller_principal())
    item = store.enqueue("agent", "task_assigned", actor="controller")
    first = store.wait("agent", timeout=0.1, visibility_timeout=0.01).item

    time.sleep(0.02)
    second = store.wait("agent", timeout=0.1, visibility_timeout=0.01).item

    assert first.inbox_id == item.inbox_id
    assert second.inbox_id == item.inbox_id
    assert second.delivered_at != first.delivered_at


def test_dedupe_key_prevents_duplicate_active_wakeups(tmp_path):
    store = InboxStore(tmp_path / "bus.sqlite3", principal=controller_principal())
    first = store.enqueue("agent", "gate_result", dedupe_key="gate:1", payload={"version": 1}, actor="controller")
    duplicate = store.enqueue("agent", "gate_result", dedupe_key="gate:1", payload={"version": 2}, actor="controller")

    assert duplicate.inbox_id == first.inbox_id
    assert duplicate.payload == {"version": 1}
    assert len(store.list_items("agent")) == 1

    delivered = store.wait("agent", timeout=0.1).item
    assert store.ack(delivered.inbox_id)
    replacement = store.enqueue("agent", "gate_result", dedupe_key="gate:1", payload={"version": 2}, actor="controller")
    assert replacement.inbox_id != first.inbox_id
    assert len(store.list_items("agent")) == 2


def test_busy_agent_receives_only_urgent_control_items(tmp_path):
    store = InboxStore(tmp_path / "bus.sqlite3", principal=controller_principal())
    ordinary = store.enqueue("agent", "task_assigned", priority=100, actor="controller")
    urgent = store.enqueue("agent", "gate_result", priority=1, actor="controller")

    busy_result = store.wait("agent", timeout=0.1, busy=True)

    assert busy_result.item.inbox_id == urgent.inbox_id
    assert busy_result.item.kind in BUSY_AGENT_DELIVERABLE_KINDS
    assert store.get(ordinary.inbox_id).status == "queued"

    assert store.ack(urgent.inbox_id)
    normal_result = store.wait("agent", timeout=0.1, busy=False)
    assert normal_result.item.inbox_id == ordinary.inbox_id


def test_human_interrupt_routes_only_to_affected_agents_and_invalidates_context(tmp_path):
    db_path = tmp_path / "bus.sqlite3"
    inbox_store = InboxStore(db_path, principal=user_principal())
    context_store = FakeContextStore(
        {
            "controller": ["ctx-controller"],
            "worker.owner": ["ctx-owner-a", "ctx-owner-b"],
            "helper.1": ["ctx-helper"],
        }
    )
    target = InterruptRoutingTarget(
        task_owner="worker.owner",
        task_assignee="worker.assignee",
        helper_agents=["helper.1", "helper.1"],
        gate_owner="qa",
        downstream_task_owners=["worker.downstream"],
    )

    result = create_user_interrupt(
        actor="user",
        target=target,
        text="Pause and replan",
        run_id="run-1",
        task_id="task-1",
        db_path=db_path,
        inbox_store=inbox_store,
        context_store=context_store,
    )

    assert result.affected_agents == [
        "controller",
        "observer",
        "worker.owner",
        "worker.assignee",
        "helper.1",
        "qa",
        "worker.downstream",
    ]
    assert compute_affected_agents(target) == result.affected_agents
    assert context_store.invalidated == [
        ("ctx-controller", result.event.event_id),
        ("ctx-owner-a", result.event.event_id),
        ("ctx-owner-b", result.event.event_id),
        ("ctx-helper", result.event.event_id),
    ]
    assert result.invalidated_packet_ids_by_agent["worker.owner"] == ["ctx-owner-a", "ctx-owner-b"]

    for agent_id in result.affected_agents:
        kinds = [item.kind for item in inbox_store.list_items(agent_id)]
        assert sorted(kinds) == ["agent_replan_required", "context_invalidated", "user_interrupt"]
        assert all(item.priority >= 980 for item in inbox_store.list_items(agent_id))

    assert inbox_store.list_items("unrelated.worker") == []
    delivered = inbox_store.wait("worker.owner", timeout=0.1, busy=True).item
    assert delivered.kind == "user_interrupt"
    assert delivered.payload["affected_agents"] == result.affected_agents
    assert delivered.payload["invalidated_packet_ids"] == ["ctx-owner-a", "ctx-owner-b"]

    events = EventStore(db_path).query_events(event_type=EventType.USER_INTERRUPT_CREATED.value)
    assert len(events) == 1
    assert events[0].payload["text"] == "Pause and replan"


def test_human_interrupt_dedupe_prevents_repeated_wakeups_for_same_event(tmp_path):
    db_path = tmp_path / "bus.sqlite3"
    inbox_store = InboxStore(db_path, principal=user_principal())
    target = InterruptRoutingTarget(task_owner="worker.owner", qa_agent=None)

    first = create_user_interrupt(
        actor="user",
        target=target,
        text="same event",
        db_path=db_path,
        inbox_store=inbox_store,
    )
    repeated = create_user_interrupt(
        actor="user",
        target=target,
        text="same event",
        db_path=db_path,
        inbox_store=inbox_store,
        event_store=StaticEventStore(first.event),
    )

    assert repeated.event.event_id == first.event.event_id
    assert len(inbox_store.list_items("worker.owner")) == 3


class FakeContextStore:
    def __init__(self, packets_by_agent):
        self.packets_by_agent = packets_by_agent
        self.invalidated = []

    def list_active_packets(self, agent_id):
        return [{"packet_id": packet_id} for packet_id in self.packets_by_agent.get(agent_id, [])]

    def invalidate_packet(self, packet_id, *, invalidated_by_event_id):
        self.invalidated.append((packet_id, invalidated_by_event_id))


class StaticEventStore:
    def __init__(self, event):
        self.event = event

    def append_event(self, event):
        return self.event
