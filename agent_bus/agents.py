from __future__ import annotations

import json
import os
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from .db import connect
from .models import (
    AgentCapability,
    AgentHealth,
    AgentIdentity,
    AgentRuntimeState,
    AgentSession,
    CapabilityEvidenceSource,
    new_id,
    utc_now_iso,
)


AGENT_SCHEMA_VERSION = 2


class AgentDirectoryError(ValueError):
    """Raised when an agent directory operation targets unknown state."""


_CAPABILITY_SOURCE_WEIGHTS: dict[CapabilityEvidenceSource, float] = {
    CapabilityEvidenceSource.DECLARED: 0.35,
    CapabilityEvidenceSource.PROBED: 0.55,
    CapabilityEvidenceSource.OBSERVED: 0.70,
    CapabilityEvidenceSource.QA_CONFIRMED: 0.85,
    CapabilityEvidenceSource.USER_ASSIGNED: 0.95,
}


_HEALTH_BY_STATE: dict[AgentRuntimeState, float] = {
    AgentRuntimeState.WAITING_ON_BUS: 0.95,
    AgentRuntimeState.WAIT_RETURNED_NOOP: 0.90,
    AgentRuntimeState.DELIVERED_NOT_ACKED: 0.70,
    AgentRuntimeState.WORKING: 0.95,
    AgentRuntimeState.SUSPECTED_STUCK: 0.30,
    AgentRuntimeState.INPUT_UNAVAILABLE: 0.25,
    AgentRuntimeState.CONTEXT_LOST: 0.35,
    AgentRuntimeState.NEEDS_REHYDRATION: 0.45,
    AgentRuntimeState.REHYDRATING: 0.65,
    AgentRuntimeState.STANDBY_READY: 1.00,
    AgentRuntimeState.STANDBY_DEGRADED: 0.55,
    AgentRuntimeState.REPLACED: 0.00,
}


class AgentDirectory:
    def __init__(
        self,
        identities: Iterable[AgentIdentity] | None = None,
        sessions: Iterable[AgentSession] | None = None,
        capabilities: Iterable[AgentCapability] | None = None,
        health_records: Iterable[AgentHealth] | None = None,
        db_path: str | os.PathLike[str] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        self._identities: dict[str, AgentIdentity] = {}
        self._sessions: dict[str, AgentSession] = {}
        self._sessions_by_agent: dict[str, list[str]] = defaultdict(list)
        self._capabilities: dict[str, AgentCapability] = {}
        self._capability_by_agent_name: dict[tuple[str, str], str] = {}
        self._health_by_session: dict[str, AgentHealth] = {}
        self.db_path = Path(db_path) if db_path is not None else None
        self.conn = conn if conn is not None else connect(self.db_path) if self.db_path is not None else None
        if self.conn is not None:
            self.conn.row_factory = sqlite3.Row
        self._owns_connection = conn is None and self.conn is not None

        if self.conn is not None:
            migrate(self.conn)
            self._load_from_db()

        for identity in identities or []:
            self._identities[identity.agent_id] = identity
            self._persist_identity(identity)
        for capability in capabilities or []:
            self._capabilities[capability.capability_id] = capability
            self._capability_by_agent_name[(capability.agent_id, capability.name)] = capability.capability_id
            identity = self._ensure_identity(capability.agent_id)
            if capability.capability_id not in identity.capability_ids:
                identity.capability_ids.append(capability.capability_id)
            self._persist_capability(capability)
            self._persist_identity(identity)
        for session in sessions or []:
            self._sessions[session.session_id] = session
            self._sessions_by_agent[session.agent_id].append(session.session_id)
            self._persist_session(session)
        for health in health_records or []:
            if health.session_id:
                self._health_by_session[health.session_id] = health
                self._persist_health(health)

    def close(self) -> None:
        if self._owns_connection and self.conn is not None:
            self.conn.close()

    def register_identity(
        self,
        agent_id: str,
        *,
        display_name: str | None = None,
        role: str | None = None,
        declared_capabilities: Iterable[str] | None = None,
    ) -> AgentIdentity:
        now = utc_now_iso()
        identity = self._identities.get(agent_id)
        if identity is None:
            identity = AgentIdentity(
                agent_id=agent_id,
                display_name=display_name,
                role=role,
                created_at=now,
                updated_at=now,
            )
            self._identities[agent_id] = identity
            self._persist_identity(identity)
        else:
            identity.display_name = display_name if display_name is not None else identity.display_name
            identity.role = role if role is not None else identity.role
            identity.updated_at = now
            self._persist_identity(identity)

        for capability_name in declared_capabilities or []:
            self.record_capability_evidence(
                agent_id,
                capability_name,
                CapabilityEvidenceSource.DECLARED,
                observed_at=now,
            )
        return identity

    def get_identity(self, agent_id: str) -> AgentIdentity:
        return self._require_identity(agent_id)

    def start_session(
        self,
        agent_id: str,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        runtime_state: AgentRuntimeState = AgentRuntimeState.STANDBY_READY,
        activate: bool = True,
    ) -> AgentSession:
        self._require_identity(agent_id)
        session_id = session_id or new_id("ses")
        if session_id in self._sessions:
            raise AgentDirectoryError(f"session already exists: {session_id}")

        if activate:
            self._deactivate_sessions(agent_id)

        now = utc_now_iso()
        session = AgentSession(
            session_id=session_id,
            agent_id=agent_id,
            run_id=run_id,
            active=activate,
            runtime_state=runtime_state,
            started_at=now,
            last_seen_at=now,
        )
        self._sessions[session_id] = session
        self._sessions_by_agent[agent_id].append(session_id)
        self._health_by_session[session_id] = self._health_for(session, reason="session started")
        self._persist_session(session)
        self._persist_health(self._health_by_session[session_id])
        return session

    def list_sessions(self, agent_id: str) -> list[AgentSession]:
        self._require_identity(agent_id)
        return [self._sessions[session_id] for session_id in self._sessions_by_agent[agent_id]]

    def list_identities(self) -> list[AgentIdentity]:
        return sorted(self._identities.values(), key=lambda identity: identity.agent_id)

    def list_all_sessions(self) -> list[AgentSession]:
        return sorted(self._sessions.values(), key=lambda session: session.started_at)

    def get_session(self, session_id: str) -> AgentSession:
        return self._require_session(session_id)

    def get_active_session(self, agent_id: str) -> AgentSession | None:
        self._require_identity(agent_id)
        for session in self.list_sessions(agent_id):
            if session.active:
                return session
        return None

    def switch_active_session(self, agent_id: str, session_id: str) -> AgentSession:
        self._require_identity(agent_id)
        session = self._require_session(session_id)
        if session.agent_id != agent_id:
            raise AgentDirectoryError(f"session {session_id} does not belong to {agent_id}")

        self._deactivate_sessions(agent_id)
        session.active = True
        session.ended_at = None
        session.last_seen_at = utc_now_iso()
        self._health_by_session[session.session_id] = self._health_for(session, reason="session activated")
        self._persist_session(session)
        self._persist_health(self._health_by_session[session.session_id])
        return session

    def update_session_state(
        self,
        session_id: str,
        runtime_state: AgentRuntimeState,
        *,
        reason: str | None = None,
    ) -> AgentHealth:
        session = self._require_session(session_id)
        session.runtime_state = runtime_state
        session.last_seen_at = utc_now_iso()
        health = self._health_for(session, reason=reason)
        self._health_by_session[session_id] = health
        self._persist_session(session)
        self._persist_health(health)
        return health

    def heartbeat_session(
        self,
        session_id: str,
        *,
        runtime_state: AgentRuntimeState | str | None = None,
        reason: str | None = None,
    ) -> AgentHealth:
        session = self._require_session(session_id)
        if not session.active or session.ended_at is not None:
            raise AgentDirectoryError(f"cannot heartbeat inactive session: {session_id}")
        if runtime_state is not None:
            session.runtime_state = AgentRuntimeState(runtime_state)
        session.last_seen_at = utc_now_iso()
        health = self._health_for(session, reason=reason or "heartbeat")
        self._health_by_session[session_id] = health
        self._persist_session(session)
        self._persist_health(health)
        return health

    def report_context_loss(self, session_id: str, *, reason: str | None = None) -> AgentHealth:
        return self.update_session_state(
            session_id,
            AgentRuntimeState.CONTEXT_LOST,
            reason=reason or "context lost",
        )

    def replace_session(
        self,
        old_session_id: str,
        replacement_session_id: str,
        *,
        reason: str | None = None,
    ) -> tuple[AgentSession, AgentSession]:
        old_session = self._require_session(old_session_id)
        replacement_session = self._require_session(replacement_session_id)
        if old_session.agent_id != replacement_session.agent_id:
            raise AgentDirectoryError("replacement session must belong to the same identity")

        old_session.active = False
        old_session.runtime_state = AgentRuntimeState.REPLACED
        old_session.replaced_by_session_id = replacement_session_id
        old_session.ended_at = utc_now_iso()
        self._health_by_session[old_session_id] = self._health_for(old_session, reason=reason or "replaced")
        self._persist_session(old_session)
        self._persist_health(self._health_by_session[old_session_id])
        self.switch_active_session(replacement_session.agent_id, replacement_session_id)
        return old_session, replacement_session

    def replace_with_session(
        self,
        old_session_id: str,
        replacement_session_id: str,
        *,
        reason: str | None = None,
        replacement_state: AgentRuntimeState = AgentRuntimeState.REHYDRATING,
    ) -> tuple[AgentSession, AgentSession]:
        old_session = self._require_session(old_session_id)
        replacement_session = self._require_session(replacement_session_id)

        old_session.active = False
        old_session.runtime_state = AgentRuntimeState.REPLACED
        old_session.replaced_by_session_id = replacement_session_id
        old_session.ended_at = utc_now_iso()
        self._health_by_session[old_session_id] = self._health_for(old_session, reason=reason or "replaced")
        self._persist_session(old_session)
        self._persist_health(self._health_by_session[old_session_id])

        self._deactivate_sessions(replacement_session.agent_id)
        replacement_session.active = True
        replacement_session.runtime_state = replacement_state
        replacement_session.ended_at = None
        replacement_session.last_seen_at = utc_now_iso()
        self._health_by_session[replacement_session_id] = self._health_for(
            replacement_session,
            reason=reason or "replacement activated",
        )
        self._persist_session(replacement_session)
        self._persist_health(self._health_by_session[replacement_session_id])
        return old_session, replacement_session

    def degrade_session(
        self,
        session_id: str,
        *,
        reason: str | None = None,
    ) -> AgentHealth:
        return self.update_session_state(
            session_id,
            AgentRuntimeState.STANDBY_DEGRADED,
            reason=reason or "degraded",
        )

    def get_health(self, session_id: str) -> AgentHealth:
        self._require_session(session_id)
        return self._health_by_session[session_id]

    def record_capability_evidence(
        self,
        agent_id: str,
        name: str,
        source: CapabilityEvidenceSource | str,
        *,
        observed_at: str | None = None,
        confidence: float | None = None,
    ) -> AgentCapability:
        identity = self._require_identity(agent_id)
        evidence_source = CapabilityEvidenceSource(source)
        observed_at = observed_at or utc_now_iso()
        key = (agent_id, name)
        capability_id = self._capability_by_agent_name.get(key)

        if capability_id is None:
            capability = AgentCapability(
                agent_id=agent_id,
                name=name,
                evidence_sources=[evidence_source],
                confidence=0.0,
                last_observed_at=observed_at,
                updated_at=observed_at,
            )
            self._capabilities[capability.capability_id] = capability
            self._capability_by_agent_name[key] = capability.capability_id
            identity.capability_ids.append(capability.capability_id)
        else:
            capability = self._capabilities[capability_id]
            if evidence_source not in capability.evidence_sources:
                capability.evidence_sources.append(evidence_source)
            capability.last_observed_at = observed_at
            capability.updated_at = utc_now_iso()

        calculated = self._combined_confidence(capability.evidence_sources)
        if confidence is not None:
            calculated = max(calculated, min(1.0, max(0.0, confidence)))
        capability.confidence = max(capability.confidence, calculated)
        identity.updated_at = utc_now_iso()
        self._persist_capability(capability)
        self._persist_identity(identity)
        return capability

    def list_capabilities(self, agent_id: str) -> list[AgentCapability]:
        identity = self._require_identity(agent_id)
        return [self._capabilities[capability_id] for capability_id in identity.capability_ids]

    def _ensure_identity(self, agent_id: str) -> AgentIdentity:
        identity = self._identities.setdefault(agent_id, AgentIdentity(agent_id=agent_id))
        self._persist_identity(identity)
        return identity

    def _require_identity(self, agent_id: str) -> AgentIdentity:
        identity = self._identities.get(agent_id)
        if identity is None:
            raise AgentDirectoryError(f"unknown agent identity: {agent_id}")
        return identity

    def _require_session(self, session_id: str) -> AgentSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise AgentDirectoryError(f"unknown agent session: {session_id}")
        return session

    def _deactivate_sessions(self, agent_id: str) -> None:
        for session_id in self._sessions_by_agent[agent_id]:
            session = self._sessions[session_id]
            session.active = False
            self._persist_session(session)

    def _health_for(self, session: AgentSession, *, reason: str | None = None) -> AgentHealth:
        return AgentHealth(
            agent_id=session.agent_id,
            session_id=session.session_id,
            runtime_state=session.runtime_state,
            health_score=_HEALTH_BY_STATE[session.runtime_state],
            stale=session.runtime_state
            in {
                AgentRuntimeState.DELIVERED_NOT_ACKED,
                AgentRuntimeState.SUSPECTED_STUCK,
                AgentRuntimeState.INPUT_UNAVAILABLE,
                AgentRuntimeState.CONTEXT_LOST,
                AgentRuntimeState.NEEDS_REHYDRATION,
            },
            input_available=session.runtime_state != AgentRuntimeState.INPUT_UNAVAILABLE,
            context_valid=session.runtime_state
            not in {
                AgentRuntimeState.CONTEXT_LOST,
                AgentRuntimeState.NEEDS_REHYDRATION,
            },
            reason=reason,
            checked_at=utc_now_iso(),
        )

    def _combined_confidence(self, sources: Iterable[CapabilityEvidenceSource]) -> float:
        miss_probability = 1.0
        for source in set(sources):
            miss_probability *= 1.0 - _CAPABILITY_SOURCE_WEIGHTS[source]
        return round(1.0 - miss_probability, 4)

    def _load_from_db(self) -> None:
        if self.conn is None:
            return
        for row in self.conn.execute("select * from agent_identities order by created_at asc").fetchall():
            identity = AgentIdentity(
                agent_id=row["agent_id"],
                display_name=row["display_name"],
                role=row["role"],
                capability_ids=json.loads(row["capability_ids_json"]),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            self._identities[identity.agent_id] = identity

        for row in self.conn.execute("select * from agent_capabilities order by updated_at asc").fetchall():
            capability = AgentCapability(
                capability_id=row["capability_id"],
                agent_id=row["agent_id"],
                name=row["name"],
                confidence=row["confidence"],
                evidence_sources=json.loads(row["evidence_sources_json"]),
                last_observed_at=row["last_observed_at"],
                updated_at=row["updated_at"],
            )
            self._capabilities[capability.capability_id] = capability
            self._capability_by_agent_name[(capability.agent_id, capability.name)] = capability.capability_id
            identity = self._ensure_identity(capability.agent_id)
            if capability.capability_id not in identity.capability_ids:
                identity.capability_ids.append(capability.capability_id)

        for row in self.conn.execute("select * from agent_sessions order by started_at asc").fetchall():
            session = AgentSession(
                session_id=row["session_id"],
                agent_id=row["agent_id"],
                run_id=row["run_id"],
                active=bool(row["active"]),
                runtime_state=row["runtime_state"],
                started_at=row["started_at"],
                last_seen_at=row["last_seen_at"],
                ended_at=row["ended_at"],
                replaced_by_session_id=row["replaced_by_session_id"],
            )
            self._sessions[session.session_id] = session
            self._sessions_by_agent[session.agent_id].append(session.session_id)

        for row in self.conn.execute("select * from agent_health").fetchall():
            health = AgentHealth(
                agent_id=row["agent_id"],
                session_id=row["session_id"],
                runtime_state=row["runtime_state"],
                health_score=row["health_score"],
                stale=bool(row["stale"]),
                input_available=bool(row["input_available"]),
                context_valid=bool(row["context_valid"]),
                reason=row["reason"],
                checked_at=row["checked_at"],
            )
            if health.session_id:
                self._health_by_session[health.session_id] = health

    def _persist_identity(self, identity: AgentIdentity) -> None:
        if self.conn is None:
            return
        self.conn.execute(
            """
            insert into agent_identities (
                agent_id, display_name, role, capability_ids_json, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?)
            on conflict(agent_id) do update set
                display_name = excluded.display_name,
                role = excluded.role,
                capability_ids_json = excluded.capability_ids_json,
                updated_at = excluded.updated_at
            """,
            (
                identity.agent_id,
                identity.display_name,
                identity.role,
                json.dumps(identity.capability_ids, sort_keys=True),
                identity.created_at,
                identity.updated_at,
            ),
        )
        self.conn.commit()

    def _persist_session(self, session: AgentSession) -> None:
        if self.conn is None:
            return
        self.conn.execute(
            """
            insert into agent_sessions (
                session_id, agent_id, run_id, active, runtime_state, started_at,
                last_seen_at, ended_at, replaced_by_session_id
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(session_id) do update set
                run_id = excluded.run_id,
                active = excluded.active,
                runtime_state = excluded.runtime_state,
                last_seen_at = excluded.last_seen_at,
                ended_at = excluded.ended_at,
                replaced_by_session_id = excluded.replaced_by_session_id
            """,
            (
                session.session_id,
                session.agent_id,
                session.run_id,
                int(session.active),
                session.runtime_state.value,
                session.started_at,
                session.last_seen_at,
                session.ended_at,
                session.replaced_by_session_id,
            ),
        )
        self.conn.commit()

    def _persist_capability(self, capability: AgentCapability) -> None:
        if self.conn is None:
            return
        self.conn.execute(
            """
            insert into agent_capabilities (
                capability_id, agent_id, name, confidence, evidence_sources_json,
                last_observed_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?)
            on conflict(capability_id) do update set
                confidence = excluded.confidence,
                evidence_sources_json = excluded.evidence_sources_json,
                last_observed_at = excluded.last_observed_at,
                updated_at = excluded.updated_at
            """,
            (
                capability.capability_id,
                capability.agent_id,
                capability.name,
                capability.confidence,
                json.dumps([source.value for source in capability.evidence_sources], sort_keys=True),
                capability.last_observed_at,
                capability.updated_at,
            ),
        )
        self.conn.commit()

    def _persist_health(self, health: AgentHealth) -> None:
        if self.conn is None or health.session_id is None:
            return
        self.conn.execute(
            """
            insert into agent_health (
                session_id, agent_id, runtime_state, health_score, stale,
                input_available, context_valid, reason, checked_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(session_id) do update set
                runtime_state = excluded.runtime_state,
                health_score = excluded.health_score,
                stale = excluded.stale,
                input_available = excluded.input_available,
                context_valid = excluded.context_valid,
                reason = excluded.reason,
                checked_at = excluded.checked_at
            """,
            (
                health.session_id,
                health.agent_id,
                health.runtime_state.value,
                health.health_score,
                int(health.stale),
                int(health.input_available),
                int(health.context_valid),
                health.reason,
                health.checked_at,
            ),
        )
        self.conn.commit()


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists schema_migrations (
            version integer primary key,
            applied_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );

        create table if not exists agent_identities (
            agent_id text primary key,
            display_name text,
            role text,
            capability_ids_json text not null,
            created_at text not null,
            updated_at text not null
        );

        create table if not exists agent_sessions (
            session_id text primary key,
            agent_id text not null,
            run_id text,
            active integer not null,
            runtime_state text not null,
            started_at text not null,
            last_seen_at text,
            ended_at text,
            replaced_by_session_id text
        );

        create index if not exists idx_agent_sessions_agent_active
        on agent_sessions(agent_id, active);

        create table if not exists agent_capabilities (
            capability_id text primary key,
            agent_id text not null,
            name text not null,
            confidence real not null,
            evidence_sources_json text not null,
            last_observed_at text,
            updated_at text not null,
            unique(agent_id, name)
        );

        create table if not exists agent_health (
            session_id text primary key,
            agent_id text not null,
            runtime_state text not null,
            health_score real not null,
            stale integer not null,
            input_available integer not null,
            context_valid integer not null,
            reason text,
            checked_at text not null
        );
        """
    )
    conn.execute(
        "insert or ignore into schema_migrations(version) values (?)",
        (AGENT_SCHEMA_VERSION,),
    )
    conn.commit()
