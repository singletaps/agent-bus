import React from "react";

import type { RuntimeStatus } from "../statusModel";

export type StatusBadgeProps = {
  status: RuntimeStatus;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span
      className={`statusBadge status-${status.color}`}
      data-action-required={status.isActionRequired ? "true" : undefined}
    >
      {status.label}
    </span>
  );
}
