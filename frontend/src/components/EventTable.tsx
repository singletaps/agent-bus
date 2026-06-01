import React from "react";

import type { EventRow } from "../operationsApi";

export type EventTableProps = {
  events: EventRow[];
};

export function EventTable({ events }: EventTableProps) {
  return (
    <div className="eventFrame">
      <table className="eventTable">
        <thead>
          <tr>
            <th>时间</th>
            <th>类型</th>
            <th>Actor</th>
            <th>目标</th>
            <th>摘要</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.id}>
              <td>{formatEventTime(event.time)}</td>
              <td>{event.type}</td>
              <td>{event.source}</td>
              <td>{event.affectedAgents[0] || "无"}</td>
              <td>{event.text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatEventTime(value: string): string {
  if (!value) {
    return "--:--:--";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleTimeString();
}
