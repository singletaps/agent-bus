from __future__ import annotations

import sqlite3

import pytest

from agent_bus.authority import (
    ensure_local_bootstrap_principals,
    resolve_local_api_principal,
)
from agent_bus.protocol_models import PrincipalType


def test_local_bootstrap_principals_are_persisted_and_resolved(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"

    ensure_local_bootstrap_principals(db_path)
    controller = resolve_local_api_principal(db_path, "controller")
    user = resolve_local_api_principal(db_path, "user")

    assert controller.principal_id == "api-controller"
    assert controller.principal_type is PrincipalType.CONTROLLER
    assert "controller" in controller.roles
    assert user.principal_id == "api-user"
    assert user.principal_type is PrincipalType.USER
    with sqlite3.connect(db_path) as conn:
        stored = {
            row[0]
            for row in conn.execute("select principal_id from principals where principal_id in ('api-controller', 'api-user', 'local-operator')")
        }
    assert stored == {"api-controller", "api-user", "local-operator"}


def test_payload_actor_cannot_mint_unrecognized_api_principal(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    ensure_local_bootstrap_principals(db_path)

    with pytest.raises(PermissionError, match="unknown local API principal"):
        resolve_local_api_principal(db_path, "worker.backend")
