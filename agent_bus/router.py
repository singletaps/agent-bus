from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .inbox import InboxStore
from .models import BusEvent, EventType
from .store import EventStore


DEFAULT_CONTROLLER_AGENT = "controller"
DEFAULT_OBSERVER_AGENT = "observer"
DEFAULT_QA_AGENT = "qa"


@dataclass(frozen=True)
class InterruptRoutingTarget:
    controller: str | None = DEFAULT_CONTROLLER_AGENT
    observer: str | None = DEFAULT_OBSERVER_AGENT
    task_owner: str | None = None
    task_assignee: str | None = None
    helper_agents: list[str] = field(default_factory=list)
    qa_agent: str | None = DEFAULT_QA_AGENT
    gate_owner: str | None = None
    downstream_task_owners: list[str] = field(default_factory=list)
    additional_agents: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InterruptRoutingResult:
    event: BusEvent
    affected_agents: list[str]
    invalidated_packet_ids_by_agent: dict[str, list[str]]
    inbox_ids_by_agent: dict[str, list[str]]


def compute_affected_agents(target: InterruptRoutingTarget) -> list[str]:
    return _ordered_unique(
        [
            target.controller,
            target.observer,
            target.task_owner,
            target.task_assignee,
            *target.helper_agents,
            target.qa_agent,
            target.gate_owner,
            *target.downstream_task_owners,
            *target.additional_agents,
        ]
    )


def create_user_interrupt(
    *,
    actor: str,
    target: InterruptRoutingTarget,
    text: str = "",
    run_id: str | None = None,
    task_id: str | None = None,
    payload: Mapping[str, Any] | None = None,
    db_path: str | os.PathLike[str] | None = None,
    event_store: EventStore | None = None,
    inbox_store: InboxStore | None = None,
    context_store: Any | None = None,
) -> InterruptRoutingResult:
    affected_agents = compute_affected_agents(target)
    event_payload = {
        "text": text,
        "affected_agents": affected_agents,
        **dict(payload or {}),
    }
    event = BusEvent(
        type=EventType.USER_INTERRUPT_CREATED,
        actor=actor,
        run_id=run_id,
        task_id=task_id,
        payload=event_payload,
    )

    event_store = event_store or EventStore(db_path)
    appended = event_store.append_event(event)

    return route_user_interrupt(
        appended,
        affected_agents=affected_agents,
        text=text,
        db_path=db_path,
        inbox_store=inbox_store,
        context_store=context_store,
    )


def route_user_interrupt(
    event: BusEvent,
    *,
    affected_agents: Iterable[str],
    text: str = "",
    db_path: str | os.PathLike[str] | None = None,
    inbox_store: InboxStore | None = None,
    context_store: Any | None = None,
) -> InterruptRoutingResult:
    agent_ids = _ordered_unique(affected_agents)
    store = inbox_store or InboxStore(db_path=db_path)
    invalidated_by_agent: dict[str, list[str]] = {}
    inbox_ids_by_agent: dict[str, list[str]] = {}
    try:
        for agent_id in agent_ids:
            packet_ids = invalidate_agent_contexts(
                context_store,
                agent_id,
                event.event_id,
                task_id=event.task_id,
                run_id=event.run_id,
            )
            invalidated_by_agent[agent_id] = packet_ids
            payload = {
                "interrupt_event_id": event.event_id,
                "run_id": event.run_id,
                "task_id": event.task_id,
                "text": text or str(event.payload.get("text", "")),
                "affected_agents": agent_ids,
            }
            items = store.enqueue_interrupt_wakeups(
                agent_id,
                payload,
                interrupt_id=event.event_id,
                context_packet_ids=packet_ids,
            )
            inbox_ids_by_agent[agent_id] = [item.inbox_id for item in items]
    finally:
        if inbox_store is None:
            store.close()

    return InterruptRoutingResult(
        event=event,
        affected_agents=agent_ids,
        invalidated_packet_ids_by_agent=invalidated_by_agent,
        inbox_ids_by_agent=inbox_ids_by_agent,
    )


def invalidate_agent_contexts(
    context_store: Any | None,
    agent_id: str,
    event_id: str,
    *,
    task_id: str | None = None,
    run_id: str | None = None,
) -> list[str]:
    if context_store is None:
        return []

    if hasattr(context_store, "invalidate_agent_contexts"):
        invalidated = context_store.invalidate_agent_contexts(
            agent_id,
            invalidated_by_event_id=event_id,
            task_id=task_id,
            run_id=run_id,
            actor="router",
        )
        return [_packet_id(packet) for packet in invalidated]

    if hasattr(context_store, "list_active_packets") and hasattr(context_store, "invalidate_packet"):
        packets = _list_active_packets(context_store, agent_id, task_id=task_id, run_id=run_id)
        invalidated_ids: list[str] = []
        for packet in packets:
            packet_id = _packet_id(packet)
            context_store.invalidate_packet(packet_id, invalidated_by_event_id=event_id)
            invalidated_ids.append(packet_id)
        return invalidated_ids

    raise TypeError(
        "context_store must provide invalidate_agent_contexts(agent_id, invalidated_by_event_id) "
        "or list_active_packets(agent_id) plus invalidate_packet(packet_id, invalidated_by_event_id)"
    )


def _ordered_unique(values: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _packet_id(packet: Any) -> str:
    if isinstance(packet, str):
        return packet
    if isinstance(packet, Mapping):
        return str(packet["packet_id"])
    return str(packet.packet_id)


def _list_active_packets(
    context_store: Any,
    agent_id: str,
    *,
    task_id: str | None,
    run_id: str | None,
) -> Iterable[Any]:
    try:
        return context_store.list_active_packets(agent_id=agent_id, task_id=task_id, run_id=run_id)
    except TypeError:
        return context_store.list_active_packets(agent_id)
