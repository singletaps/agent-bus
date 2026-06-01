from __future__ import annotations

import json

from fastapi.testclient import TestClient

from agent_bus.agents import AgentDirectory
from agent_bus.artifacts import read_artifact_manifests
from agent_bus.gates import GateBoard
from agent_bus.server import create_app


def test_artifact_manifest_reader_ignores_paths_outside_root(tmp_path):
    root = tmp_path / ".agent-bus" / "artifacts" / "run_1" / "task_1"
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(
        json.dumps(
            [
                {
                    "artifact_id": "art_ok",
                    "run_id": "run_1",
                    "task_id": "task_1",
                    "agent_id": "worker",
                    "type": "screenshot",
                    "title": "Home",
                    "path": "home.png",
                },
                {"artifact_id": "art_bad", "type": "log", "title": "Bad", "path": "../../../outside.log"},
            ]
        ),
        encoding="utf-8",
    )
    (root / "home.png").write_bytes(b"png")

    result = read_artifact_manifests(tmp_path / ".agent-bus" / "artifacts")

    assert [item.artifact_id for item in result.artifacts] == ["art_ok"]
    assert result.artifacts[0].path == "run_1/task_1/home.png"
    assert result.artifacts[0].size_bytes == 3
    assert result.artifacts[0].content_type == "image/png"
    assert result.artifacts[0].preview_url == "/api/artifacts/files/run_1/task_1/home.png"
    assert result.artifacts[0].download_url == "/api/artifacts/files/run_1/task_1/home.png?download=1"


def test_artifact_manifest_api_uses_configured_root(tmp_path, monkeypatch):
    artifact_root = tmp_path / "artifacts" / "run_1" / "task_1"
    artifact_root.mkdir(parents=True)
    (artifact_root / "manifest.json").write_text(
        json.dumps({"artifact_id": "art_1", "type": "report", "title": "QA report", "path": "qa.md"}),
        encoding="utf-8",
    )
    (artifact_root / "qa.md").write_text("ok", encoding="utf-8")
    monkeypatch.setenv("AGENT_BUS_ARTIFACT_ROOT", str(tmp_path / "artifacts"))

    client = TestClient(create_app(db_path=tmp_path / "bus.sqlite3", frontend_dist=tmp_path / "missing-dist"))
    response = client.get("/api/artifacts/manifests").json()

    assert response["ok"] is True
    assert response["artifacts"][0]["artifact_id"] == "art_1"
    assert response["artifacts"][0]["path"] == "run_1/task_1/qa.md"
    assert response["artifacts"][0]["size_bytes"] == 2
    assert response["artifacts"][0]["content_type"] == "text/markdown"
    assert response["artifacts"][0]["preview_url"] == "/api/artifacts/files/run_1/task_1/qa.md"

    file_response = client.get(response["artifacts"][0]["preview_url"])
    assert file_response.status_code == 200
    assert file_response.text == "ok"
    assert file_response.headers["content-type"].split(";")[0] == "text/markdown"

    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    traversal = client.get("/api/artifacts/files/..%2Fsecret.txt")
    assert traversal.status_code == 400

    missing = client.get("/api/artifacts/files/run_1/task_1/missing.md")
    assert missing.status_code == 404


def test_gate_owner_projection_prefers_qa_without_mutating_durable_gate(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    AgentDirectory(db_path=db_path).register_identity("runtime-qa", role="qa")
    gates = GateBoard(db_path=db_path)
    gate = gates.create_gate("Contract QA", run_id="run-1", task_id="task-1", requested_by="helper")

    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))
    projected_gate = client.get("/api/projections/operations").json()["gates"][0]

    assert projected_gate["gate_id"] == gate.gate_id
    assert projected_gate["owner_agent_id"] == "runtime-qa"
    assert gates.get_gate(gate.gate_id).owner_agent_id is None
