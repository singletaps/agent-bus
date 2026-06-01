from __future__ import annotations

import json
import sqlite3

from agent_bus.__main__ import main


def test_gate1_init_register_and_wait_json_path(tmp_path, capsys):
    db_path = tmp_path / "agent-bus.sqlite3"

    assert main(["init", "--reset", "--db", str(db_path), "--json"]) == 0
    init_output = json.loads(capsys.readouterr().out)

    assert init_output == {"db": str(db_path), "ok": True, "reset": True}
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type = 'table'")}
    assert {"event_log", "inbox_items", "schema_migrations"} <= tables

    assert (
        main(
            [
                "agent",
                "register",
                "controller",
                "--role",
                "controller",
                "--db",
                str(db_path),
                "--json",
            ]
        )
        == 0
    )
    register_output = json.loads(capsys.readouterr().out)

    assert register_output["ok"] is True
    assert register_output["identity"]["agent_id"] == "controller"
    assert register_output["identity"]["role"] == "controller"
    assert register_output["session"]["agent_id"] == "controller"
    assert register_output["session"]["active"] is True
    assert [event["type"] for event in register_output["events"]] == [
        "agent.registered",
        "agent.session_started",
    ]

    with sqlite3.connect(db_path) as conn:
        event_count = conn.execute("select count(*) from event_log").fetchone()[0]
    assert event_count == 2

    assert main(["wait", "--agent", "controller", "--timeout", "0.01", "--db", str(db_path), "--json"]) == 0
    wait_output = json.loads(capsys.readouterr().out)

    assert wait_output["ok"] is True
    assert wait_output["item"] is None
    assert wait_output["kind"] == "noop"
    assert wait_output["noop"] is True
    assert wait_output["timed_out"] is True
    assert wait_output["session"]["runtime_state"] == "WAIT_RETURNED_NOOP"
