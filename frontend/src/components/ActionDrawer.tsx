import React, { type CSSProperties, useEffect, useMemo, useState } from "react";

import type { AgentRow } from "../operationsApi";
import { IdChip } from "./IdChip";

export type ActionDrawerKind = "task" | "gate" | "message" | "artifact";

export type ActionDrawerCommand =
  | "message_controller"
  | "reassign"
  | "request_qa"
  | "open_gate"
  | "view_artifact"
  | "mark_known";

export type ActionDrawerItem = {
  kind: ActionDrawerKind;
  id: string;
  title: string;
  runId?: string;
  taskId?: string;
  suggestedActions: ActionDrawerCommand[];
};

export type ActionDrawerSubmitPayload = {
  item: ActionDrawerItem;
  action: ActionDrawerCommand;
  message: string;
  targetAgentId: string;
};

export type ActionDrawerProps = {
  agents: AgentRow[];
  item: ActionDrawerItem | null;
  status: string;
  onClose: () => void;
  onSubmit: (payload: ActionDrawerSubmitPayload) => void;
};

const actionLabels: Record<ActionDrawerCommand, string> = {
  message_controller: "通知 Controller",
  reassign: "重新分派",
  request_qa: "请求 QA",
  open_gate: "处理门禁",
  view_artifact: "查看产物",
  mark_known: "标记已知",
};

const actionDescriptions: Record<ActionDrawerCommand, string> = {
  message_controller: "通过 Agent Bus 通知调度方。",
  reassign: "请求重新分派负责人或执行 Agent。",
  request_qa: "让 QA 补充判断、验证或裁决。",
  open_gate: "发起门禁处理请求，不直接修改后端门禁状态。",
  view_artifact: "请求对方查看关联产物或报告。",
  mark_known: "记录已知状态并让相关 Agent 继续。",
};

const kindLabels: Record<ActionDrawerKind, string> = {
  task: "任务",
  gate: "门禁",
  message: "消息",
  artifact: "产物",
};

export function ActionDrawer({
  agents,
  item,
  status,
  onClose,
  onSubmit,
}: ActionDrawerProps) {
  const [action, setAction] = useState<ActionDrawerCommand>("message_controller");
  const [message, setMessage] = useState("");
  const [targetAgentId, setTargetAgentId] = useState("");

  const visibleAgents = useMemo(
    () => agents.filter((agent) => agent.id || agent.name),
    [agents],
  );
  const actions = item?.suggestedActions.length
    ? item.suggestedActions
    : (["message_controller"] as ActionDrawerCommand[]);

  useEffect(() => {
    if (!item) {
      return;
    }
    const nextAction = item.suggestedActions[0] || "message_controller";
    setAction(nextAction);
    setMessage(defaultMessage(item, nextAction));
    setTargetAgentId("");
  }, [item]);

  if (!item) {
    return null;
  }

  return (
    <aside aria-label="行动详情" className="actionDrawer" style={styles.shell}>
      <form
        className="panel"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({ item, action, message, targetAgentId });
        }}
        style={styles.form}
      >
        <header className="panelHeader">
          <div style={styles.headerCopy}>
            <span className="eyebrow">{kindLabels[item.kind]}</span>
            <h3>{item.title}</h3>
          </div>
          <button className="filterButton" onClick={onClose} type="button">
            关闭
          </button>
        </header>

        <div style={styles.linkRow}>
          <IdChip label="对象" value={item.id} />
          {item.runId ? <IdChip label="Run" value={item.runId} /> : null}
          {item.taskId ? <IdChip label="Task" value={item.taskId} /> : null}
        </div>

        <section style={styles.actionGrid} aria-label="可执行动作">
          {actions.map((candidate) => (
            <button
              aria-pressed={action === candidate}
              className="segmentButton"
              key={candidate}
              onClick={() => {
                setAction(candidate);
                setMessage(defaultMessage(item, candidate));
              }}
              style={action === candidate ? styles.selectedAction : undefined}
              type="button"
            >
              <strong>{actionLabels[candidate]}</strong>
              <span>{actionDescriptions[candidate]}</span>
            </button>
          ))}
        </section>

        <label className="fieldStack" style={styles.field}>
          <span>目标 Agent</span>
          <select
            onChange={(event) => setTargetAgentId(event.target.value)}
            value={targetAgentId}
          >
            <option value="">按关联上下文投递</option>
            {visibleAgents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name || agent.id}
              </option>
            ))}
          </select>
        </label>

        <label className="fieldStack" style={styles.field}>
          <span>发送内容</span>
          <textarea
            onChange={(event) => setMessage(event.target.value)}
            rows={7}
            value={message}
          />
        </label>

        <div className="labelRow" style={styles.routeRow}>
          <span>投递通道</span>
          <strong>Agent Bus</strong>
        </div>
        {status ? <p className="syncLine" style={styles.statusLine}>{status}</p> : null}

        <button className="commandButton" disabled={!message.trim()} style={styles.primaryButton} type="submit">
          发送到 Agent Bus
        </button>
      </form>
    </aside>
  );
}

function defaultMessage(item: ActionDrawerItem, action: ActionDrawerCommand): string {
  if (item.kind === "gate") {
    if (action === "open_gate") {
      return `请处理门禁：${item.title}`;
    }
    if (action === "request_qa") {
      return `请 QA 补充门禁判断：${item.title}`;
    }
    if (action === "message_controller") {
      return `请 Controller 关注门禁决策：${item.title}`;
    }
    return `门禁动作待确认：${item.title}`;
  }
  if (item.kind === "artifact") {
    return `请查看产物：${item.title}`;
  }
  if (item.kind === "message") {
    return `请确认消息：${item.title}`;
  }
  if (action === "reassign") {
    return `请重新分派任务：${item.title}`;
  }
  return `请处理任务：${item.title}`;
}

const styles: Record<string, CSSProperties> = {
  shell: {
    bottom: 16,
    display: "grid",
    maxWidth: "calc(100vw - 32px)",
    position: "fixed",
    right: 16,
    top: 16,
    width: 440,
    zIndex: 40,
  },
  form: {
    display: "grid",
    gap: 14,
    overflow: "auto",
    padding: 0,
  },
  headerCopy: {
    minWidth: 0,
  },
  linkRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    padding: "12px 14px 0",
  },
  actionGrid: {
    display: "grid",
    gap: 8,
    padding: "0 14px",
  },
  selectedAction: {
    borderColor: "#2563eb",
    background: "#eff6ff",
    color: "#2563eb",
  },
  field: {
    display: "grid",
    gap: 6,
    padding: "0 14px",
  },
  routeRow: {
    borderTop: "1px solid #e2e8f0",
    padding: "12px 14px 0",
  },
  statusLine: {
    margin: "0 14px",
  },
  primaryButton: {
    justifySelf: "stretch",
    margin: "0 14px 14px",
    background: "#2563eb",
    color: "#ffffff",
  },
};
