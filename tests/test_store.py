from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

from agent_bus.db import initialize_database
from agent_bus.models import BusEvent, EventType
from agent_bus.store import EventStore


def test_initialize_database_creates_migration_and_event_log(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"

    initialize_database(db_path)

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type = 'table'")}
        journal_mode = conn.execute("pragma journal_mode").fetchone()[0]
        migration = conn.execute("select version from schema_migrations").fetchone()[0]

    assert "schema_migrations" in tables
    assert "event_log" in tables
    assert journal_mode == "wal"
    assert migration == 1


def test_append_and_get_event_round_trips_payload_and_correlation(tmp_path):
    store = EventStore(tmp_path / "agent-bus.sqlite3")
    event = BusEvent(
        type=EventType.TASK_CREATED,
        actor="controller",
        run_id="run-1",
        task_id="task-1",
        agent_id="worker.backend",
        correlation_id="corr-1",
        causation_id="cause-1",
        payload={"title": "Build store", "count": 2},
    )

    appended = store.append_event(event)
    loaded = store.get_event(event.event_id)

    assert appended.seq == 1
    assert loaded is not None
    assert loaded.payload == {"title": "Build store", "count": 2}
    assert loaded.correlation_id == "corr-1"
    assert loaded.causation_id == "cause-1"
    assert loaded.seq == 1


def test_query_events_orders_and_filters(tmp_path):
    store = EventStore(tmp_path / "agent-bus.sqlite3")
    first = store.append_event(BusEvent(type="custom.alpha", run_id="run-1", agent_id="a", payload={"n": 1}))
    second = store.append_event(BusEvent(type="custom.beta", run_id="run-1", agent_id="b", payload={"n": 2}))
    store.append_event(BusEvent(type="custom.alpha", run_id="run-2", agent_id="a", payload={"n": 3}))

    assert [event.event_id for event in store.replay_all()] == [
        first.event_id,
        second.event_id,
        store.query_events(run_id="run-2")[0].event_id,
    ]
    assert [event.payload["n"] for event in store.query_events(event_type="custom.alpha")] == [1, 3]
    assert [event.payload["n"] for event in store.query_events(after_seq=first.seq, run_id="run-1")] == [2]
    assert [event.payload["n"] for event in store.query_events(agent_id="a", limit=1)] == [1]


def test_concurrent_append_uses_stable_increasing_sequence(tmp_path):
    store = EventStore(tmp_path / "agent-bus.sqlite3")

    def append_one(index: int):
        return store.append_event(BusEvent(type="custom.concurrent", payload={"index": index}))

    with ThreadPoolExecutor(max_workers=8) as executor:
        appended = list(executor.map(append_one, range(20)))

    replayed = store.replay_all()
    seqs = [event.seq for event in replayed]

    assert sorted(event.seq for event in appended if event.seq is not None) == list(range(1, 21))
    assert seqs == list(range(1, 21))
    assert len({event.event_id for event in replayed}) == 20

