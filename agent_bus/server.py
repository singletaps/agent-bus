from __future__ import annotations

import asyncio
import json
import mimetypes
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agents import AgentDirectory, AgentDirectoryError
from .artifacts import ArtifactManifestItem, ArtifactPathError, read_artifact_manifests, resolve_artifact_file
from .context import ContextPacketInvalidated, ContextPacketNotFound, ContextStore
from .db import initialize_database
from .inbox import InboxStore
from .models import (
    AgentHealth,
    AgentRuntimeState,
    AgentSession,
    BusEvent,
    BusMessageProjection,
    ContextPacket,
    EventType,
    InboxItem,
    RunRecord,
    TaskRecord,
    new_id,
)
from .projections import (
    AgentProjection,
    OperationsProjection,
    ProjectionReader,
    ReplacementRecommendationProjection,
    SessionProjection,
    build_message_projection,
    build_operations_projection,
)
from .replacement import (
    ReplacementCandidate,
    ReplacementCoordinator,
    ReplacementRecommendation,
    ReplacementTrigger,
)
from .router import InterruptRoutingTarget, create_user_interrupt
from .store import EventStore


class ApiEnvelope(BaseModel):
    ok: bool = True


class AgentsResponse(ApiEnvelope):
    agents: list[AgentProjection]


class AgentHeartbeatRequest(BaseModel):
    session_id: str | None = None
    runtime_state: AgentRuntimeState | None = None
    reason: str | None = "heartbeat"


class AgentHeartbeatResponse(ApiEnvelope):
    session: AgentSession
    health: AgentHealth
    event: BusEvent


class SessionsResponse(ApiEnvelope):
    sessions: list[SessionProjection]


class RunsResponse(ApiEnvelope):
    runs: list[RunRecord]


class TasksResponse(ApiEnvelope):
    tasks: list[TaskRecord]


class MessagesResponse(ApiEnvelope):
    messages: list[BusMessageProjection]


class BusMessageSendRequest(BaseModel):
    actor: str = "operator"
    text: str
    recipient_agent_ids: list[str] = Field(default_factory=list)
    run_id: str | None = None
    task_id: str | None = None
    gate_id: str | None = None
    message_type: str = "instruction"
    priority: str = "normal"


class BusMessageSendResponse(ApiEnvelope):
    event: BusEvent
    affected_agents: list[str]


class ArtifactManifestApiResponse(ApiEnvelope):
    root: str
    artifacts: list[ArtifactManifestItem]


class InboxWaitRequest(BaseModel):
    agent_id: str
    timeout: float = Field(default=300.0, ge=0.0)
    busy: bool = False
    visibility_timeout: float = Field(default=30.0, gt=0.0)
    poll_interval: float = Field(default=0.05, gt=0.0)


class InboxWaitResponse(ApiEnvelope):
    kind: str
    noop: bool
    timed_out: bool
    item: InboxItem | None = None


class InboxAckRequest(BaseModel):
    inbox_id: str
    agent_id: str | None = None


class InboxAckResponse(ApiEnvelope):
    inbox_id: str
    acked: bool


class InterruptTargetPayload(BaseModel):
    controller: str | None = "controller"
    observer: str | None = "observer"
    task_owner: str | None = None
    task_assignee: str | None = None
    helper_agents: list[str] = Field(default_factory=list)
    qa_agent: str | None = "qa"
    gate_owner: str | None = None
    downstream_task_owners: list[str] = Field(default_factory=list)
    additional_agents: list[str] = Field(default_factory=list)


class InterruptRequest(BaseModel):
    actor: str
    text: str = ""
    run_id: str | None = None
    task_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    target: InterruptTargetPayload


class InterruptResponse(ApiEnvelope):
    event: BusEvent
    affected_agents: list[str]
    invalidated_packet_ids_by_agent: dict[str, list[str]]
    inbox_ids_by_agent: dict[str, list[str]]


class ReplacementRecommendationsResponse(ApiEnvelope):
    recommendations: list[ReplacementRecommendationProjection]


class ReplacementApproveRequest(BaseModel):
    recommendation_id: str | None = None
    task_id: str
    old_session_id: str
    old_agent_id: str | None = None
    candidate_agent_id: str
    candidate_session_id: str | None = None
    run_id: str | None = None
    trigger_names: list[str] = Field(default_factory=list)
    reason: str | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    role: str | None = None
    approved_by: str = "controller"
    next_action: str = "continue the same task from the rehydration packet"
    required_artifacts: list[str] = Field(default_factory=list)
    invalidated_packet_ids: list[str] = Field(default_factory=list)


class ReplacementApproveResponse(ApiEnvelope):
    recommendation_id: str
    task_id: str
    old_session: Any
    replacement_session: Any
    context_packet: ContextPacket
    approved_by: str


def create_app(
    *,
    db_path: str | os.PathLike[str] | None = None,
    frontend_dist: str | os.PathLike[str] | None = None,
) -> FastAPI:
    initialize_database(db_path)
    app = FastAPI(title="Agent Bus Runtime API", version="0.1.0")
    app.state.db_path = db_path
    app.state.frontend_dist = _resolve_frontend_dist(frontend_dist)

    @app.get("/api/events/stream")
    async def events_stream(
        request: Request,
        after_seq: int | None = Query(default=None, ge=0),
        poll_interval: float = Query(default=0.25, gt=0),
        event_limit: int = Query(default=200, ge=0),
        include_snapshot: bool = Query(default=True),
        max_events: int | None = Query(default=None, ge=1),
    ) -> StreamingResponse:
        return StreamingResponse(
            _operations_sse(
                request,
                after_seq=after_seq,
                poll_interval=poll_interval,
                event_limit=event_limit,
                include_snapshot=include_snapshot,
                max_events=max_events,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/agents", response_model=AgentsResponse)
    def agents(request: Request) -> AgentsResponse:
        projection = _projection(request)
        return AgentsResponse(agents=projection.agents)

    @app.post("/api/agents/{agent_id}/heartbeat", response_model=AgentHeartbeatResponse)
    def agent_heartbeat(agent_id: str, payload: AgentHeartbeatRequest, request: Request) -> AgentHeartbeatResponse:
        db = _db_path(request)
        directory = AgentDirectory(db_path=db)
        store = EventStore(db)
        try:
            try:
                session = directory.get_session(payload.session_id) if payload.session_id else directory.get_active_session(agent_id)
            except AgentDirectoryError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            if session is None:
                raise HTTPException(status_code=404, detail=f"no active session for agent: {agent_id}")
            if session.agent_id != agent_id:
                raise HTTPException(status_code=400, detail="session does not belong to agent")
            try:
                health = directory.heartbeat_session(
                    session.session_id,
                    runtime_state=payload.runtime_state,
                    reason=payload.reason,
                )
            except AgentDirectoryError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            session = directory.get_session(session.session_id)
            event = store.append_event(
                BusEvent(
                    type=EventType.AGENT_STATUS_CHANGED,
                    actor=agent_id,
                    agent_id=agent_id,
                    run_id=session.run_id,
                    payload={
                        "session": session.model_dump(mode="json"),
                        "health": health.model_dump(mode="json"),
                        "reason": payload.reason or "heartbeat",
                    },
                )
            )
            return AgentHeartbeatResponse(session=session, health=health, event=event)
        finally:
            directory.close()

    @app.get("/api/sessions", response_model=SessionsResponse)
    def sessions(request: Request) -> SessionsResponse:
        projection = _projection(request)
        return SessionsResponse(sessions=projection.sessions)

    @app.get("/api/runs", response_model=RunsResponse)
    def runs(request: Request) -> RunsResponse:
        projection = _projection(request)
        return RunsResponse(runs=projection.runs)

    @app.get("/api/tasks", response_model=TasksResponse)
    def tasks(request: Request) -> TasksResponse:
        projection = _projection(request)
        return TasksResponse(tasks=projection.tasks)

    @app.get("/api/projections/messages", response_model=MessagesResponse)
    def messages_projection(request: Request, event_limit: int = Query(default=200, ge=0)) -> MessagesResponse:
        reader = ProjectionReader(_db_path(request))
        projection = reader.build_operations_projection(event_limit=event_limit)
        return MessagesResponse(messages=build_message_projection(projection.events, projection.inbox))

    @app.post("/api/messages/send", response_model=BusMessageSendResponse)
    def send_message(payload: BusMessageSendRequest, request: Request) -> BusMessageSendResponse:
        db = _db_path(request)
        context = ContextStore(db)
        try:
            result = create_user_interrupt(
                actor=payload.actor,
                target=InterruptRoutingTarget(
                    controller=None,
                    observer=None,
                    qa_agent=None,
                    additional_agents=payload.recipient_agent_ids,
                ),
                text=payload.text,
                run_id=payload.run_id,
                task_id=payload.task_id,
                payload={
                    "message_id": new_id("msg"),
                    "message_type": payload.message_type,
                    "priority": payload.priority,
                    "gate_id": payload.gate_id,
                    "reply_state": "not_required",
                },
                db_path=db,
                context_store=context,
            )
        finally:
            context.close()
        return BusMessageSendResponse(event=result.event, affected_agents=result.affected_agents)

    @app.get("/api/artifacts/manifests", response_model=ArtifactManifestApiResponse)
    def artifact_manifests(request: Request) -> ArtifactManifestApiResponse:
        manifests = read_artifact_manifests(_artifact_root(request))
        return ArtifactManifestApiResponse(root=manifests.root, artifacts=manifests.artifacts)

    @app.get("/api/artifacts/files/{artifact_path:path}")
    def artifact_file(
        artifact_path: str,
        request: Request,
        download: bool = Query(default=False),
    ) -> FileResponse:
        try:
            path = resolve_artifact_file(_artifact_root(request), artifact_path)
        except ArtifactPathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="artifact file not found") from exc
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if download:
            return FileResponse(path, media_type=content_type, filename=path.name)
        return FileResponse(path, media_type=content_type)

    @app.post("/api/inbox/wait", response_model=InboxWaitResponse)
    async def inbox_wait(payload: InboxWaitRequest, request: Request) -> InboxWaitResponse:
        db = _db_path(request)
        deadline = asyncio.get_running_loop().time() + payload.timeout
        store = InboxStore(db_path=db)
        try:
            while True:
                if await request.is_disconnected():
                    raise HTTPException(status_code=499, detail="client disconnected")
                result = await asyncio.to_thread(
                    store.wait,
                    payload.agent_id,
                    0,
                    busy=payload.busy,
                    visibility_timeout=payload.visibility_timeout,
                    poll_interval=payload.poll_interval,
                )
                if result.item is not None or asyncio.get_running_loop().time() >= deadline:
                    return InboxWaitResponse(
                        kind=result.kind,
                        noop=result.noop,
                        timed_out=result.timed_out,
                        item=result.item,
                    )
                await asyncio.sleep(min(payload.poll_interval, max(deadline - asyncio.get_running_loop().time(), 0)))
        finally:
            store.close()

    @app.post("/api/inbox/ack", response_model=InboxAckResponse)
    def inbox_ack(payload: InboxAckRequest, request: Request) -> InboxAckResponse:
        store = InboxStore(db_path=_db_path(request))
        try:
            acked = store.ack(payload.inbox_id, agent_id=payload.agent_id)
            return InboxAckResponse(inbox_id=payload.inbox_id, acked=acked)
        finally:
            store.close()

    @app.get("/api/context/{packet_id}", response_model=ContextPacket)
    def context_packet(
        packet_id: str,
        request: Request,
        include_inactive: bool = Query(default=False),
    ) -> ContextPacket:
        try:
            return ProjectionReader(_db_path(request)).get_context_packet(packet_id, include_inactive=include_inactive)
        except ContextPacketInvalidated as exc:
            return JSONResponse(status_code=409, content=exc.to_payload())
        except ContextPacketNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/interrupt", response_model=InterruptResponse)
    def interrupt(payload: InterruptRequest, request: Request) -> InterruptResponse:
        db = _db_path(request)
        context = ContextStore(db)
        try:
            result = create_user_interrupt(
                actor=payload.actor,
                target=InterruptRoutingTarget(**payload.target.model_dump()),
                text=payload.text,
                run_id=payload.run_id,
                task_id=payload.task_id,
                payload=payload.payload,
                db_path=db,
                context_store=context,
            )
        finally:
            context.close()
        return InterruptResponse(
            event=result.event,
            affected_agents=result.affected_agents,
            invalidated_packet_ids_by_agent=result.invalidated_packet_ids_by_agent,
            inbox_ids_by_agent=result.inbox_ids_by_agent,
        )

    @app.get("/api/replacement/recommendations", response_model=ReplacementRecommendationsResponse)
    def replacement_recommendations(
        request: Request,
        session_id: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
        required_capability: list[str] = Query(default_factory=list),
        role: str | None = None,
    ) -> ReplacementRecommendationsResponse:
        recommendations = ProjectionReader(_db_path(request)).replacement_recommendations(
            session_id=session_id,
            task_id=task_id,
            run_id=run_id,
            required_capabilities=required_capability,
            role=role,
        )
        return ReplacementRecommendationsResponse(recommendations=recommendations)

    @app.post("/api/replacement/approve", response_model=ReplacementApproveResponse)
    def replacement_approve(payload: ReplacementApproveRequest, request: Request) -> ReplacementApproveResponse:
        db = _db_path(request)
        directory = AgentDirectory(db_path=db)
        inbox = InboxStore(db_path=db)
        context = ContextStore(db)
        coordinator = ReplacementCoordinator(
            directory=directory,
            inbox=inbox,
            context_sink=context,
            event_store=EventStore(db),
            db_path=db,
        )
        try:
            recommendation = _approval_recommendation(payload)
            approval = coordinator.approve(
                recommendation,
                approved_by=payload.approved_by,
                next_action=payload.next_action,
                required_artifacts=payload.required_artifacts,
                invalidated_packet_ids=payload.invalidated_packet_ids,
            )
            return ReplacementApproveResponse(
                recommendation_id=recommendation.recommendation_id,
                task_id=approval.task_id,
                old_session=approval.old_session.model_dump(mode="json"),
                replacement_session=approval.replacement_session.model_dump(mode="json"),
                context_packet=approval.context_packet,
                approved_by=approval.approved_by,
            )
        finally:
            directory.close()
            inbox.close()
            context.close()

    @app.get("/api/projections/operations", response_model=OperationsProjection)
    def operations_projection(request: Request, event_limit: int = Query(default=200, ge=0)) -> OperationsProjection:
        return build_operations_projection(_db_path(request), event_limit=event_limit)

    frontend_root = app.state.frontend_dist
    if frontend_root is not None and frontend_root.exists():
        _ensure_static_mime_types()
        app.mount("/", StaticFiles(directory=str(frontend_root), html=True), name="frontend")

    return app


async def _operations_sse(
    request: Request,
    *,
    after_seq: int | None,
    poll_interval: float,
    event_limit: int,
    include_snapshot: bool,
    max_events: int | None,
) -> AsyncIterator[str]:
    sent = 0
    db = _db_path(request)
    last_seq = after_seq
    if include_snapshot:
        projection = build_operations_projection(db, event_limit=event_limit)
        last_seq = projection.last_seq
        sent += 1
        yield _sse("operations", projection.model_dump(mode="json"))
        if max_events is not None and sent >= max_events:
            return

    while True:
        if await request.is_disconnected():
            return
        reader = ProjectionReader(db)
        events = reader.events_after(last_seq, limit=event_limit)
        if events:
            projection = reader.build_operations_projection(event_limit=event_limit)
            last_seq = projection.last_seq
            sent += 1
            yield _sse("operations", projection.model_dump(mode="json"))
            if max_events is not None and sent >= max_events:
                return
        await asyncio.sleep(poll_interval)


def _projection(request: Request) -> OperationsProjection:
    return build_operations_projection(_db_path(request))


def _db_path(request: Request) -> str | os.PathLike[str] | None:
    return request.app.state.db_path


def _artifact_root(request: Request) -> str:
    root = os.environ.get("AGENT_BUS_ARTIFACT_ROOT")
    if root is not None:
        return root
    db_path = _db_path(request)
    base_dir = Path(db_path).resolve().parent if db_path is not None else Path(".").resolve()
    return str(base_dir / ".agent-bus" / "artifacts")


def _resolve_frontend_dist(frontend_dist: str | os.PathLike[str] | None) -> Path | None:
    if frontend_dist is not None:
        return Path(frontend_dist)
    candidate = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    return candidate if candidate.exists() else None


def _ensure_static_mime_types() -> None:
    for extension, content_type in {
        ".js": "application/javascript",
        ".mjs": "application/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".map": "application/json",
        ".wasm": "application/wasm",
    }.items():
        mimetypes.add_type(content_type, extension, strict=True)
        mimetypes.add_type(content_type, extension, strict=False)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, sort_keys=True)}\n\n"


def _approval_recommendation(payload: ReplacementApproveRequest) -> ReplacementRecommendation:
    triggers = tuple(
        ReplacementTrigger(name=name, reason=payload.reason or name, weight=1.0)
        for name in (payload.trigger_names or ["manual_controller_approval"])
    )
    candidate = ReplacementCandidate(
        agent_id=payload.candidate_agent_id,
        session_id=payload.candidate_session_id,
        score=1.0,
        capability_score=1.0,
        readiness_score=1.0,
        role_score=1.0,
        freshness_score=1.0,
        failure_penalty=0.0,
    )
    return ReplacementRecommendation(
        recommendation_id=payload.recommendation_id or f"api_{payload.old_session_id}_{payload.candidate_agent_id}",
        task_id=payload.task_id,
        old_session_id=payload.old_session_id,
        old_agent_id=payload.old_agent_id or payload.old_session_id,
        candidate=candidate,
        triggers=triggers,
        run_id=payload.run_id,
        required_capabilities=tuple(payload.required_capabilities),
        role=payload.role,
    )


app = create_app()
