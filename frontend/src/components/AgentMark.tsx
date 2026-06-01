import React from "react";

import {
  Archive,
  CircuitBoard,
  CircleHelp,
  Command,
  Hammer,
  ScanEye,
} from "lucide-react";

import type { AgentRow } from "../operationsApi";
import { statusFromState } from "../statusModel";
import { StatusBadge } from "./StatusBadge";

type AgentMarkProps = {
  agent: AgentRow;
  compact?: boolean;
};

const roleIcons = {
  controller: Command,
  helper: CircuitBoard,
  observer: Archive,
  qa: ScanEye,
  worker: Hammer,
};

const roleLabels: Record<string, string> = {
  controller: "controller command",
  helper: "helper circuit",
  observer: "observer archive",
  qa: "QA scan",
  worker: "worker tool",
};

export function AgentMark({ agent, compact = false }: AgentMarkProps) {
  const role = preferredRole(agent.roles, agent.role);
  const Icon = roleIcons[role as keyof typeof roleIcons] || CircleHelp;
  const status = statusFromState(agent.state, "agent");
  const label = roleLabels[role] || role;

  return (
    <div
      aria-label={`${agent.name || agent.id} ${label}`}
      className="agentMark"
      data-compact={compact ? "true" : undefined}
      data-role={role}
      data-status={status.color}
    >
      <span className="agentMarkIcon" title={label}>
        <Icon aria-hidden="true" size={compact ? 15 : 18} strokeWidth={2.25} />
      </span>
      <div className="agentMarkText">
        <strong>{agent.name || agent.id}</strong>
        <span>{agent.roles.length ? agent.roles.join(" / ") : agent.role}</span>
      </div>
      {!compact ? <StatusBadge status={status} /> : null}
    </div>
  );
}

function preferredRole(roles: string[], fallback: string): string {
  const normalized = [...roles, fallback]
    .map((role) => role.toLowerCase())
    .filter(Boolean);
  const roleKeywords: Array<[string, string[]]> = [
    ["controller", ["controller", "dispatcher", "command", "console"]],
    ["qa", ["qa", "reviewer", "gatekeeper"]],
    ["helper", ["helper", "bootstrapper", "support"]],
    ["worker", ["worker", "runtime", "cli-worker"]],
    ["observer", ["observer", "archive", "docs"]],
  ];

  for (const [role, keywords] of roleKeywords) {
    if (normalized.some((value) => keywords.some((keyword) => value.includes(keyword)))) {
      return role;
    }
  }
  return fallback.toLowerCase() || "worker";
}
