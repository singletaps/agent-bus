import type { Tone } from "./operationsApi";

export type RuntimeStatusColor =
  | "green"
  | "yellow"
  | "red"
  | "gray"
  | "purple"
  | "blue";

export type RuntimeStatus = {
  label: string;
  tone: Tone;
  color: RuntimeStatusColor;
  isActionRequired: boolean;
};

export function statusFromState(
  state: string,
  kind: "task" | "gate" | "agent" | "run" | "message",
): RuntimeStatus {
  const label = state || "无数据";
  const value = label.toLowerCase().replace(/[_-]/g, " ");

  if (
    ["fail", "failed", "block", "blocked", "reject", "rejected", "invalid", "stuck"].some(
      (part) => value.includes(part),
    )
  ) {
    return { label, tone: "bad", color: "red", isActionRequired: true };
  }

  if (["review", "qa"].some((part) => value.includes(part))) {
    return {
      label,
      tone: "info",
      color: "purple",
      isActionRequired: kind === "gate",
    };
  }

  if (
    [
      "wait",
      "waiting",
      "pending",
      "queued",
      "assigned",
      "acknowledged",
      "working",
      "progress",
      "open",
      "escalated",
    ].some((part) => value.includes(part))
  ) {
    return {
      label,
      tone: "warn",
      color: "yellow",
      isActionRequired: value.includes("open") || value.includes("escalated"),
    };
  }

  if (
    ["done", "complete", "completed", "pass", "passed", "approved", "acked"].some(
      (part) => value.includes(part),
    )
  ) {
    return { label, tone: "good", color: "green", isActionRequired: false };
  }

  if (
    ["created", "not started", "unknown", "none", "no data"].some((part) =>
      value.includes(part),
    )
  ) {
    return { label, tone: "info", color: "gray", isActionRequired: false };
  }

  return { label, tone: "info", color: "gray", isActionRequired: false };
}
