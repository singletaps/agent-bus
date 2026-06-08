from __future__ import annotations

import pytest

from agent_bus.authority import controller_principal
from agent_bus.inbox import InboxStore
from agent_bus.models import TaskState
from agent_bus.reviews import ReviewBoard
from agent_bus.tasks import TaskBoard


def test_request_changes_rejects_self_review(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    reviews = ReviewBoard(db_path=db_path)

    with pytest.raises(PermissionError, match="reviewer cannot request changes on their own work"):
        reviews.request_changes(
            run_id="run-1",
            task_id="task-1",
            worker_agent_id="runtime-worker-5",
            reviewer_agent_id="runtime-worker-5",
            findings=[
                {
                    "severity": "P1",
                    "category": "contract",
                    "evidence": "worker is reviewing its own gate contract",
                    "requested_change": "use independent qa/controller review",
                    "blocking": True,
                }
            ],
        )

    assert InboxStore(db_path).list_items("runtime-worker-5") == []


def test_request_changes_does_not_complete_or_fail_task(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    tasks = TaskBoard(db_path=db_path, principal=controller_principal())
    run = tasks.create_run("Review flow", created_by="controller")
    task = tasks.create_task("Implement review contract", run_id=run.run_id, owner_agent_id="controller")
    assigned = tasks.assign_task(task.task_id, "runtime-worker-5", actor="controller")
    tasks.acknowledge_task(assigned.task_id, actor="runtime-worker-5")
    tasks.start_task(assigned.task_id, actor="runtime-worker-5")

    findings = ReviewBoard(db_path=db_path).request_changes(
        run_id=run.run_id,
        task_id=task.task_id,
        worker_agent_id="runtime-worker-5",
        reviewer_agent_id="runtime-qa",
        findings=[
            {
                "severity": "P1",
                "category": "contract",
                "evidence": "approval lacks linked gate evidence",
                "requested_change": "require related evidence before approval",
                "blocking": True,
            }
        ],
    )

    assert len(findings) == 1
    assert tasks.get_task(task.task_id).status is TaskState.WORKING
    changes = [item for item in InboxStore(db_path).list_items("runtime-worker-5") if item.kind == "changes_requested"]
    assert len(changes) == 1
    assert changes[0].payload["task_id"] == task.task_id
