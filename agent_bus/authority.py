from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from types import MappingProxyType

from .db import connect, initialize_database
from .protocol_models import AuthorityDecision, Principal, PrincipalType


CONTROLLER_ACTIONS = frozenset(
    {
        "controller.commit",
        "run.created",
        "task.created",
        "task.assigned",
        "task.acknowledged",
        "task.started",
        "task.progress",
        "task.blocked",
        "task.completed",
        "task.failed",
        "task.claim_rejected",
        "task.reassigned",
        "task.superseded",
        "artifact.created",
        "coordination.recorded",
        "context.created",
        "context.invalidated",
        "context.superseded",
        "inbox.enqueued",
        "gate.opened",
        "gate.approve",
        "gate.approved",
        "gate.reject",
        "gate.rejected",
        "gate.escalated",
        "replacement.approved",
        "replacement.reassignment_committed",
    }
)

WORKER_ACTIONS = frozenset(
    {
        "worker.claim",
        "task.ack_claimed",
        "task.progress_reported",
        "task.blocker_reported",
        "task.completion_claimed",
        "task.failure_claimed",
        "artifact.produced",
        "handoff.proposed",
        "context.replan_requested",
        "worker.heartbeat",
    }
)

SYSTEM_ACTIONS = CONTROLLER_ACTIONS | WORKER_ACTIONS | frozenset(
    {
        "protocol.violation_recorded",
        "projection.effect_recorded",
        "adapter.deprecated_path_used",
    }
)


@dataclass(frozen=True)
class DirectAuthorityMutation:
    path: str
    replacement: str
    reason: str


DIRECT_AUTHORITATIVE_MUTATORS = MappingProxyType(
    {
        "agent_bus.tasks.TaskBoard.complete_task": DirectAuthorityMutation(
            path="agent_bus.tasks.TaskBoard.complete_task",
            replacement="ProtocolKernel controller claim commit",
            reason="workers and legacy callers must not complete tasks directly",
        ),
        "agent_bus.tasks.TaskBoard.fail_task": DirectAuthorityMutation(
            path="agent_bus.tasks.TaskBoard.fail_task",
            replacement="ProtocolKernel controller claim reject/fail",
            reason="task failure is an authoritative controller transition",
        ),
        "agent_bus.gates.GateBoard.approve_gate": DirectAuthorityMutation(
            path="agent_bus.gates.GateBoard.approve_gate",
            replacement="ProtocolKernel gate decision",
            reason="gate approval needs principal and no-self-review policy checks",
        ),
        "agent_bus.replacement.ReplacementCoordinator.approve": DirectAuthorityMutation(
            path="agent_bus.replacement.ReplacementCoordinator.approve",
            replacement="ProtocolKernel replacement approval",
            reason="replacement approval must be split from reassignment commit",
        ),
    }
)


class AuthorityService:
    """Static principal/role authority checks for protocol writes."""

    def evaluate(
        self,
        *,
        actor: str | None,
        actor_role: str | None,
        action: str,
        principal: Principal | None = None,
    ) -> AuthorityDecision:
        normalized_action = _normalize_action(action)
        roles = _roles_for(actor_role, principal)
        principal_type = principal.principal_type if principal is not None else None

        if principal is None:
            return AuthorityDecision(
                allowed=False,
                reason="authenticated principal is required for protocol authority",
                action=normalized_action,
                actor=actor,
                actor_role=actor_role,
                principal_id=None,
            )

        if principal is not None and (
            normalized_action in principal.permissions or "*" in principal.permissions
        ):
            return AuthorityDecision(
                allowed=True,
                action=normalized_action,
                actor=actor,
                actor_role=actor_role,
                principal_id=principal.principal_id,
            )

        if principal_type is PrincipalType.SYSTEM or "system" in roles:
            return _allow(actor, actor_role, normalized_action, principal)

        if principal_type in {PrincipalType.CONTROLLER, PrincipalType.USER} or roles & {"controller", "user"}:
            if normalized_action in CONTROLLER_ACTIONS or normalized_action in SYSTEM_ACTIONS:
                return _allow(actor, actor_role, normalized_action, principal)

        if principal_type is PrincipalType.AGENT or roles & {"worker", "agent", "qa"}:
            if normalized_action in WORKER_ACTIONS:
                return _allow(actor, actor_role, normalized_action, principal)

        return AuthorityDecision(
            allowed=False,
            reason=f"actor role is not authorized for {normalized_action}",
            action=normalized_action,
            actor=actor,
            actor_role=actor_role,
            principal_id=principal.principal_id if principal else None,
        )


def is_direct_authoritative_mutator(path: str) -> bool:
    return path in DIRECT_AUTHORITATIVE_MUTATORS


def system_principal(
    principal_id: str = "system",
    *,
    permissions: list[str] | None = None,
) -> Principal:
    return Principal(
        principal_id=principal_id,
        principal_type=PrincipalType.SYSTEM,
        roles=["system"],
        permissions=permissions or ["*"],
    )


def controller_principal(
    principal_id: str = "controller",
    *,
    permissions: list[str] | None = None,
) -> Principal:
    return Principal(
        principal_id=principal_id,
        principal_type=PrincipalType.CONTROLLER,
        roles=["controller"],
        permissions=permissions or [],
    )


def user_principal(
    principal_id: str = "user",
    *,
    permissions: list[str] | None = None,
) -> Principal:
    return Principal(
        principal_id=principal_id,
        principal_type=PrincipalType.USER,
        roles=["user"],
        permissions=permissions or [],
    )


def local_operator_principal(
    principal_id: str = "local-operator",
    *,
    permissions: list[str] | None = None,
) -> Principal:
    return Principal(
        principal_id=principal_id,
        principal_type=PrincipalType.CONTROLLER,
        roles=["controller", "operator"],
        permissions=permissions or [],
    )


LOCAL_API_PRINCIPAL_IDS = MappingProxyType(
    {
        "controller": "api-controller",
        "api-controller": "api-controller",
        "user": "api-user",
        "api-user": "api-user",
        "operator": "local-operator",
        "local-operator": "local-operator",
    }
)


def ensure_local_bootstrap_principals(db_path: str | os.PathLike[str] | None = None) -> None:
    initialize_database(db_path)
    principals = (
        controller_principal("api-controller"),
        user_principal("api-user"),
        local_operator_principal("local-operator"),
    )
    with connect(db_path) as conn:
        for principal in principals:
            conn.execute(
                """
                insert into principals (
                    principal_id, principal_type, agent_id, session_id,
                    roles_json, permissions_json, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(principal_id) do update set
                    principal_type = excluded.principal_type,
                    agent_id = excluded.agent_id,
                    session_id = excluded.session_id,
                    roles_json = excluded.roles_json,
                    permissions_json = excluded.permissions_json,
                    updated_at = excluded.updated_at
                """,
                _principal_row_values(principal),
            )


def resolve_local_api_principal(
    db_path: str | os.PathLike[str] | None,
    actor: str,
) -> Principal:
    ensure_local_bootstrap_principals(db_path)
    principal_id = LOCAL_API_PRINCIPAL_IDS.get(actor)
    if principal_id is None:
        raise PermissionError(f"unknown local API principal: {actor}")
    with connect(db_path) as conn:
        row = conn.execute("select * from principals where principal_id = ?", (principal_id,)).fetchone()
    if row is None:
        raise PermissionError(f"local API principal is not provisioned: {principal_id}")
    return _principal_from_row(row)


def agent_principal(
    agent_id: str,
    *,
    session_id: str | None = None,
    principal_id: str | None = None,
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
) -> Principal:
    return Principal(
        principal_id=principal_id or f"agent:{agent_id}",
        principal_type=PrincipalType.AGENT,
        agent_id=agent_id,
        session_id=session_id,
        roles=roles or ["worker"],
        permissions=permissions or [],
    )


def actor_role_for_principal(principal: Principal | None, fallback: str | None = None) -> str | None:
    if principal is None:
        return fallback
    if principal.principal_type is PrincipalType.SYSTEM:
        return "system"
    if principal.principal_type is PrincipalType.CONTROLLER:
        return "controller"
    if principal.principal_type is PrincipalType.USER:
        return "user"
    if principal.principal_type is PrincipalType.AGENT:
        if principal.roles:
            return principal.roles[0]
        return "agent"
    return fallback


def _allow(
    actor: str | None,
    actor_role: str | None,
    action: str,
    principal: Principal | None,
) -> AuthorityDecision:
    return AuthorityDecision(
        allowed=True,
        action=action,
        actor=actor,
        actor_role=actor_role,
        principal_id=principal.principal_id if principal else None,
    )


def _roles_for(actor_role: str | None, principal: Principal | None) -> set[str]:
    roles = {role.lower() for role in principal.roles} if principal is not None else set()
    if actor_role:
        roles.add(actor_role.lower())
    return roles


def _principal_row_values(principal: Principal) -> tuple[object, ...]:
    return (
        principal.principal_id,
        principal.principal_type.value,
        principal.agent_id,
        principal.session_id,
        json.dumps(principal.roles, sort_keys=True),
        json.dumps(principal.permissions, sort_keys=True),
        principal.created_at,
        principal.updated_at,
    )


def _principal_from_row(row: sqlite3.Row) -> Principal:
    return Principal(
        principal_id=row["principal_id"],
        principal_type=PrincipalType(row["principal_type"]),
        agent_id=row["agent_id"],
        session_id=row["session_id"],
        roles=json.loads(row["roles_json"] or "[]"),
        permissions=json.loads(row["permissions_json"] or "[]"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _normalize_action(action: str) -> str:
    return action.value if hasattr(action, "value") else str(action)
