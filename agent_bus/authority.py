from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

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


def _normalize_action(action: str) -> str:
    return action.value if hasattr(action, "value") else str(action)
