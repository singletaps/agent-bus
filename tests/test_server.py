from __future__ import annotations

from fastapi.testclient import TestClient

from agent_bus.agents import AgentDirectory
from agent_bus.context import ContextStore
from agent_bus.gates import GateBoard
from agent_bus.inbox import InboxStore
from agent_bus.models import AgentRuntimeState, BusEvent, CapabilityEvidenceSource
from agent_bus.server import create_app
from agent_bus.store import EventStore
from agent_bus.tasks import TaskBoard


def test_operations_api_projects_durable_runtime_state_and_openapi(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("worker.backend", role="worker", declared_capabilities=["python"])
    directory.start_session("worker.backend", session_id="session-backend")
    directory.record_capability_evidence("worker.backend", "python", CapabilityEvidenceSource.QA_CONFIRMED)
    board = TaskBoard(db_path=db_path, agent_directory=directory)
    run = board.create_run("Wave C", objective="Expose API", created_by="controller")
    task = board.create_task(
        "Implement FastAPI server",
        run_id=run.run_id,
        owner_agent_id="controller",
        assignee_agent_id="worker.backend",
    )
    ContextStore(db_path).create_packet(
        agent_id="worker.backend",
        run_id=run.run_id,
        task_id=task.task_id,
        summary="API work",
    )

    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    agents = client.get("/api/agents").json()
    tasks = client.get("/api/tasks").json()
    projection = client.get("/api/projections/operations").json()
    openapi = client.get("/openapi.json")

    assert agents["ok"] is True
    assert agents["agents"][0]["identity"]["agent_id"] == "worker.backend"
    assert agents["agents"][0]["active_session"]["session_id"] == "session-backend"
    assert agents["agents"][0]["capabilities"][0]["name"] == "python"
    assert tasks["tasks"][0]["task_id"] == task.task_id
    assert projection["metrics"]["agents"] == 1
    assert projection["replay_state"]["tasks"][task.task_id]["status"] == "assigned"
    assert projection["last_seq"] >= 3
    assert openapi.status_code == 200
    assert "/api/inbox/wait" in openapi.json()["paths"]


def test_operations_api_projects_run_state_from_task_progression(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("worker.backend", role="worker")
    directory.start_session("worker.backend", session_id="worker-session")
    board = TaskBoard(db_path=db_path, agent_directory=directory)
    run = board.create_run("Progressed run", objective="Avoid stale created status", created_by="controller")
    task = board.create_task(
        "Advance task",
        run_id=run.run_id,
        owner_agent_id="controller",
        assignee_agent_id="worker.backend",
    )
    board.acknowledge_task(task.task_id, actor="worker.backend")
    board.start_task(task.task_id, actor="worker.backend")
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    projection = client.get("/api/projections/operations").json()
    projected_run = next(item for item in projection["runs"] if item["run_id"] == run.run_id)
    projected_task = next(item for item in projection["tasks"] if item["task_id"] == task.task_id)

    assert projected_run["status"] == "active"
    assert projected_task["status"] == "working"
    assert projection["replay_state"]["runs"][run.run_id]["status"] == "active"
    assert projection["replay_state"]["tasks"][task.task_id]["status"] == "working"


def test_operations_api_projects_ui_metro_and_durable_artifacts(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("controller", role="controller")
    directory.register_identity("runtime-qa", role="qa")
    directory.register_identity("worker.frontend", role="worker", declared_capabilities=["react"])
    directory.start_session("worker.frontend", session_id="frontend-session")
    board = TaskBoard(db_path=db_path, agent_directory=directory)
    run = board.create_run("Reference convergence", objective="Match 5-29 pages", created_by="controller")
    task = board.create_task(
        "Build metro graph",
        run_id=run.run_id,
        owner_agent_id="controller",
        assignee_agent_id="worker.frontend",
    )
    board.acknowledge_task(task.task_id, actor="worker.frontend")
    board.start_task(task.task_id, actor="worker.frontend")
    gate = GateBoard(db_path=db_path).create_gate(
        "QA approval",
        run_id=run.run_id,
        task_id=task.task_id,
        requested_by="worker.frontend",
        risk="high",
    )
    artifact = board.create_artifact(
        "screenshot",
        "run_1/task_1/home.png",
        run_id=run.run_id,
        task_id=task.task_id,
        metadata={"title": "Home screenshot"},
        created_by="worker.frontend",
    )

    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))
    projection = client.get("/api/projections/operations").json()

    assert projection["artifacts"][0]["artifact_id"] == artifact.artifact_id
    assert projection["metrics"]["artifacts"] == 1
    assert projection["ui"]["active_run"]["run_id"] == run.run_id
    assert projection["ui"]["active_run"]["progress"]["active"] == 1

    nodes = projection["ui"]["metro"]["nodes"]
    node_ids = {node["id"] for node in nodes}
    assert f"task:{task.task_id}" in node_ids
    assert f"gate:{gate.gate_id}" in node_ids
    assert f"artifact:{artifact.artifact_id}" in node_ids
    assert projection["ui"]["metro"]["branch_groups"][f"task:{task.task_id}"] == [
        f"gate:{gate.gate_id}",
        f"artifact:{artifact.artifact_id}",
    ]
    assert any(item["kind"] == "gate" and item["gate_id"] == gate.gate_id for item in projection["ui"]["action_items"])
    assert projection["ui"]["artifact_summary"]["latest_artifact_id"] == artifact.artifact_id
    assert projection["ui"]["agent_summaries"][0]["agent_id"] in {"controller", "runtime-qa", "worker.frontend"}


def test_operations_api_derives_stale_session_health_from_missed_heartbeat(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("runtime-qa", role="qa")
    session = directory.start_session("runtime-qa", session_id="qa-session")
    directory.conn.execute(
        "update agent_sessions set last_seen_at = ? where session_id = ?",
        ("2026-05-28T00:00:00Z", session.session_id),
    )
    directory.conn.commit()
    directory.close()
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    agents = client.get("/api/agents").json()["agents"]
    sessions = client.get("/api/sessions").json()["sessions"]

    assert agents[0]["active_session"]["runtime_state"] == "STANDBY_DEGRADED"
    assert agents[0]["health"]["runtime_state"] == "STANDBY_DEGRADED"
    assert agents[0]["health"]["stale"] is True
    assert agents[0]["health"]["health_score"] < 1.0
    assert "missing heartbeat" in agents[0]["health"]["reason"]
    assert sessions[0]["session"]["runtime_state"] == "STANDBY_DEGRADED"
    assert sessions[0]["health"]["stale"] is True


def test_operations_api_keeps_explicit_recent_session_state_fresh(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("worker.backend", role="worker")
    session = directory.start_session("worker.backend", session_id="worker-session")
    directory.conn.execute(
        "update agent_sessions set last_seen_at = ? where session_id = ?",
        ("2026-05-28T00:00:00Z", session.session_id),
    )
    directory.conn.commit()
    directory.update_session_state(session.session_id, AgentRuntimeState.WORKING, reason="active task progress")
    directory.close()
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    agent = client.get("/api/agents").json()["agents"][0]

    assert agent["active_session"]["runtime_state"] == "WORKING"
    assert agent["health"]["runtime_state"] == "WORKING"
    assert agent["health"]["stale"] is False
    assert agent["health"]["reason"] == "active task progress"


def test_agent_heartbeat_api_refreshes_stale_session_and_records_event(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("runtime-qa", role="qa")
    session = directory.start_session("runtime-qa", session_id="qa-session")
    directory.conn.execute(
        "update agent_sessions set last_seen_at = ? where session_id = ?",
        ("2026-05-28T00:00:00Z", session.session_id),
    )
    directory.conn.commit()
    directory.close()
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    stale = client.get("/api/agents").json()["agents"][0]
    heartbeat = client.post(
        "/api/agents/runtime-qa/heartbeat",
        json={"reason": "qa poll alive"},
    ).json()
    refreshed = client.get("/api/agents").json()["agents"][0]
    projection = client.get("/api/projections/operations").json()

    assert stale["health"]["stale"] is True
    assert heartbeat["ok"] is True
    assert heartbeat["session"]["runtime_state"] == "STANDBY_READY"
    assert heartbeat["health"]["stale"] is False
    assert heartbeat["event"]["type"] == "agent.status_changed"
    assert heartbeat["event"]["payload"]["reason"] == "qa poll alive"
    assert refreshed["active_session"]["runtime_state"] == "STANDBY_READY"
    assert refreshed["health"]["stale"] is False
    assert projection["last_seq"] == heartbeat["event"]["seq"]


def test_inbox_wait_and_ack_api_return_actionable_item_then_noop(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    item = InboxStore(db_path).enqueue("worker.frontend", "task_assigned", {"task_id": "task-1"})
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    delivered = client.post(
        "/api/inbox/wait",
        json={"agent_id": "worker.frontend", "timeout": 1, "poll_interval": 0.01},
    ).json()

    assert delivered["ok"] is True
    assert delivered["noop"] is False
    assert delivered["item"]["inbox_id"] == item.inbox_id
    assert delivered["item"]["payload"] == {"task_id": "task-1"}

    acked = client.post("/api/inbox/ack", json={"inbox_id": item.inbox_id, "agent_id": "worker.frontend"}).json()
    assert acked == {"ok": True, "inbox_id": item.inbox_id, "acked": True}

    noop = client.post(
        "/api/inbox/wait",
        json={"agent_id": "worker.frontend", "timeout": 0.01, "poll_interval": 0.005},
    ).json()
    assert noop["noop"] is True
    assert noop["timed_out"] is True
    assert noop["item"] is None


def test_context_api_returns_structured_invalidated_error(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    context = ContextStore(db_path)
    packet = context.create_packet(agent_id="worker", summary="old")
    invalidated = context.invalidate_packet(packet.packet_id, invalidated_by_event_id="evt-stop")
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    blocked = client.get(f"/api/context/{packet.packet_id}")
    inactive = client.get(f"/api/context/{packet.packet_id}?include_inactive=true")
    missing = client.get("/api/context/missing")

    assert blocked.status_code == 409
    assert blocked.json()["error"] == "context_packet_invalidated"
    assert blocked.json()["invalidated_by_event_id"] == "evt-stop"
    assert inactive.status_code == 200
    assert inactive.json()["status"] == "invalidated"
    assert inactive.json()["invalidated_at"] == invalidated.invalidated_at
    assert missing.status_code == 404


def test_interrupt_api_routes_only_affected_agents_and_invalidates_context(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    context = ContextStore(db_path)
    affected = context.create_packet(agent_id="worker.owner", run_id="run-1", task_id="task-1", summary="affected")
    context.create_packet(agent_id="worker.unrelated", run_id="run-1", task_id="task-1", summary="unrelated")
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    response = client.post(
        "/api/interrupt",
        json={
            "actor": "user",
            "text": "Pause for replan",
            "run_id": "run-1",
            "task_id": "task-1",
            "target": {
                "controller": "controller",
                "observer": "observer",
                "task_owner": "worker.owner",
                "task_assignee": "worker.assignee",
                "helper_agents": ["helper.1"],
                "qa_agent": "qa",
            },
        },
    ).json()

    assert response["ok"] is True
    assert response["affected_agents"] == [
        "controller",
        "observer",
        "worker.owner",
        "worker.assignee",
        "helper.1",
        "qa",
    ]
    assert response["invalidated_packet_ids_by_agent"]["worker.owner"] == [affected.packet_id]
    assert context.get_packet(affected.packet_id, include_inactive=True).status == "invalidated"
    assert InboxStore(db_path).list_items("worker.unrelated") == []
    owner_kinds = {item.kind for item in InboxStore(db_path).list_items("worker.owner")}
    assert owner_kinds == {"user_interrupt", "context_invalidated", "agent_replan_required"}


def test_replacement_recommendation_and_approval_api_rehydrates_candidate(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("worker.frontend", role="worker", declared_capabilities=["react"])
    old = directory.start_session("worker.frontend", run_id="run-1", session_id="old-session")
    directory.register_identity("worker.spare", role="worker", declared_capabilities=["react"])
    spare = directory.start_session("worker.spare", run_id="run-1", session_id="spare-session")
    directory.record_capability_evidence("worker.spare", "react", CapabilityEvidenceSource.QA_CONFIRMED)
    directory.report_context_loss(old.session_id, reason="context compression failed")
    board = TaskBoard(db_path=db_path, agent_directory=directory)
    task = board.create_task(
        "Build console",
        run_id="run-1",
        owner_agent_id="controller",
        assignee_agent_id="worker.frontend",
    )
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    recommendations = client.get(
        "/api/replacement/recommendations",
        params={
            "session_id": old.session_id,
            "task_id": task.task_id,
            "required_capability": "react",
            "role": "worker",
        },
    ).json()["recommendations"]

    assert len(recommendations) == 1
    recommendation = recommendations[0]
    assert recommendation["old_session_id"] == old.session_id
    assert recommendation["candidate"]["agent_id"] == "worker.spare"

    approval = client.post(
        "/api/replacement/approve",
        json={
            "recommendation_id": recommendation["recommendation_id"],
            "task_id": task.task_id,
            "old_session_id": old.session_id,
            "old_agent_id": recommendation["old_agent_id"],
            "candidate_agent_id": "worker.spare",
            "candidate_session_id": spare.session_id,
            "run_id": "run-1",
            "trigger_names": [trigger["name"] for trigger in recommendation["triggers"]],
            "approved_by": "controller",
            "next_action": "continue implementation",
            "required_artifacts": ["artifact://diff"],
        },
    ).json()

    assert approval["ok"] is True
    assert approval["context_packet"]["agent_id"] == "worker.spare"
    assert approval["context_packet"]["instructions"]["kind"] == "rehydration"
    assert approval["context_packet"]["instructions"]["next_action"] == "continue implementation"
    reassigned = TaskBoard(db_path=db_path).get_task(task.task_id)
    assert reassigned.assignee_agent_id == "worker.spare"
    assert reassigned.status.value == "reassigned"
    assert AgentDirectory(db_path=db_path).get_session(old.session_id).runtime_state is AgentRuntimeState.REPLACED
    notice = InboxStore(db_path).wait("worker.spare", timeout=0.1).item
    assert notice.kind in {"task_assigned", "replacement_notice"}
    if notice.kind != "replacement_notice":
        notice = InboxStore(db_path).wait("worker.spare", timeout=0.1).item
    assert notice.kind == "replacement_notice"
    assert notice.context_packet_id == approval["context_packet"]["packet_id"]


def test_sse_emits_operations_snapshot_and_static_frontend_is_served(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    dist = tmp_path / "dist"
    assets = dist / "assets"
    dist.mkdir()
    assets.mkdir()
    (assets / "index-test.js").write_text("console.log('agent-bus');", encoding="utf-8")
    (dist / "index.html").write_text(
        '<html><body><div id="root">Agent Bus</div><script type="module" src="/assets/index-test.js"></script></body></html>',
        encoding="utf-8",
    )
    EventStore(db_path).append_event(BusEvent(type="test.event", actor="test", payload={"ok": True}))
    client = TestClient(create_app(db_path=db_path, frontend_dist=dist))

    with client.stream("GET", "/api/events/stream?max_events=1&poll_interval=0.01") as response:
        body = response.read().decode("utf-8")

    assert "event: operations" in body
    assert '"last_seq": 1' in body

    static = client.get("/")
    assert static.status_code == 200
    assert "Agent Bus" in static.text
    module = client.get("/assets/index-test.js")
    assert module.status_code == 200
    assert module.headers["content-type"].split(";")[0] in {"application/javascript", "text/javascript"}
