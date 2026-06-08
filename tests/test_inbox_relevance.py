from datetime import datetime, timedelta, timezone

from agent_bus.authority import controller_principal
from agent_bus.inbox import InboxStore
from agent_bus.models import InboxRelevanceState
from agent_bus.relevance import derive_inbox_relevance


def old_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def test_replaced_session_queued_inbox_is_diagnostics_only(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    inbox = InboxStore(db_path=db_path, principal=controller_principal())
    item = inbox.enqueue("sim2-frontend", "replacement_notice", {"task_id": "task-1"}, actor="controller")

    result = derive_inbox_relevance(
        inbox=[item],
        owner_authority_valid_by_agent={"sim2-frontend": False},
        now_iso=old_iso(0),
    )

    assert result[item.inbox_id].relevance_state is InboxRelevanceState.DIAGNOSTICS_ONLY
    assert result[item.inbox_id].blocks_identity_archive is False


def test_delivered_item_with_expired_lease_is_lease_expired(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    inbox = InboxStore(db_path=db_path, principal=controller_principal())
    item = inbox.enqueue("worker", "task_assigned", {"task_id": "task-1"}, actor="controller")
    delivered = item.model_copy(update={"status": "delivered", "lease_expires_at": old_iso(60)})

    result = derive_inbox_relevance(
        inbox=[delivered],
        owner_authority_valid_by_agent={"worker": True},
        now_iso=old_iso(0),
    )

    assert result[delivered.inbox_id].relevance_state is InboxRelevanceState.LEASE_EXPIRED
    assert result[delivered.inbox_id].blocks_identity_archive is True
