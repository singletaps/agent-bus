import React, { type CSSProperties, useState } from "react";

import type {
  AgentRow,
  ArtifactManifestRow,
  BusMessageRow,
  GateRow,
  RunRow,
} from "../operationsApi";
import { statusFromState } from "../statusModel";
import { IdChip } from "./IdChip";
import { Panel } from "./Panel";
import { StatusBadge } from "./StatusBadge";

type DetailRailProps = {
  agent?: AgentRow;
  artifact?: ArtifactManifestRow;
  gate?: GateRow;
  message?: BusMessageRow;
  run?: RunRow;
  title?: string;
};

type RailTab = "message" | "agent";

export function DetailRail({
  agent,
  artifact,
  gate,
  message,
  run,
  title = "详情",
}: DetailRailProps) {
  const [activeTab, setActiveTab] = useState<RailTab>("message");
  const hasDetail = Boolean(agent || artifact || gate || message || run);
  const showTabs = Boolean(message && agent);
  const showMessage = Boolean(message && (!showTabs || activeTab === "message"));
  const showAgent = Boolean(agent && (!showTabs || activeTab === "agent"));

  return (
    <Panel className="detailRail" title={title} meta={hasDetail ? "实时事实" : "等待选择"}>
      {!hasDetail ? (
        <div className="referenceEmpty" style={styles.empty}>
          <strong>等待选择对象</strong>
          <span>选择一条消息、门禁、运行或 Agent 后，这里会显示事实、链路和下一步出口。</span>
        </div>
      ) : null}

      {showTabs ? (
        <div className="referenceTabs" style={styles.tabs}>
          <button
            aria-pressed={activeTab === "message"}
            onClick={() => setActiveTab("message")}
            type="button"
          >
            消息详情
          </button>
          <button
            aria-pressed={activeTab === "agent"}
            onClick={() => setActiveTab("agent")}
            type="button"
          >
            Agent 详情
          </button>
        </div>
      ) : null}

      {showMessage && message ? <MessageDetail message={message} /> : null}
      {showAgent && agent ? <AgentDetail agent={agent} /> : null}
      {gate ? <GateDetail gate={gate} /> : null}
      {run ? <RunDetail run={run} /> : null}
      {artifact ? <ArtifactDetail artifact={artifact} /> : null}
    </Panel>
  );
}

function MessageDetail({ message }: { message: BusMessageRow }) {
  return (
    <div style={styles.section}>
      <div style={styles.badgeRow}>
        <StatusBadge status={statusFromState(message.deliveryState, "message")} />
        <StatusBadge status={statusFromState(message.ackState, "message")} />
        <StatusBadge status={statusFromState(message.replyState, "message")} />
      </div>
      <dl className="detailGrid" style={styles.grid}>
        <dt>消息 ID</dt>
        <dd>
          <IdChip value={message.messageId} />
        </dd>
        <dt>发送方</dt>
        <dd>{message.senderName || message.senderAgentId || "system"}</dd>
        <dt>收件人</dt>
        <dd>{message.recipientAgentIds.join(", ") || "广播"}</dd>
        <dt>发送时间</dt>
        <dd>{formatDateTime(message.createdAt)}</dd>
        <dt>最后更新</dt>
        <dd>{formatDateTime(message.updatedAt)}</dd>
        <dt>消息内容</dt>
        <dd style={styles.bodyCell}>{message.body || "无正文"}</dd>
      </dl>
      <ContextLinks message={message} />
      <MessageTrack message={message} />
    </div>
  );
}

function AgentDetail({ agent }: { agent: AgentRow }) {
  return (
    <dl className="detailGrid" style={styles.grid}>
      <dt>Agent</dt>
      <dd>{agent.name || agent.id}</dd>
      <dt>角色</dt>
      <dd>{agent.roles.join(" / ") || agent.role}</dd>
      <dt>运行状态</dt>
      <dd>
        <StatusBadge status={statusFromState(agent.state, "agent")} />
      </dd>
      <dt>会话</dt>
      <dd>
        <IdChip value={agent.sessionId || "no-session"} />
      </dd>
      <dt>Inbox</dt>
      <dd>{agent.inboxCount}</dd>
      <dt>能力</dt>
      <dd>{agent.capabilities.join(" / ") || "未声明"}</dd>
    </dl>
  );
}

function GateDetail({ gate }: { gate: GateRow }) {
  return (
    <dl className="detailGrid" style={styles.grid}>
      <dt>门禁</dt>
      <dd>{gate.name}</dd>
      <dt>状态</dt>
      <dd>
        <StatusBadge status={statusFromState(gate.state, "gate")} />
      </dd>
      <dt>负责人</dt>
      <dd>{gate.owner || "未记录"}</dd>
      <dt>请求方</dt>
      <dd>{gate.requestedBy || "未记录"}</dd>
      <dt>任务</dt>
      <dd>{gate.taskId ? <IdChip value={gate.taskId} /> : "未关联"}</dd>
      <dt>原因</dt>
      <dd style={styles.bodyCell}>{gate.reason || "未记录"}</dd>
    </dl>
  );
}

function RunDetail({ run }: { run: RunRow }) {
  return (
    <dl className="detailGrid" style={styles.grid}>
      <dt>Run</dt>
      <dd>{run.title}</dd>
      <dt>状态</dt>
      <dd>
        <StatusBadge status={statusFromState(run.state, "run")} />
      </dd>
      <dt>Owner</dt>
      <dd>{run.owner}</dd>
      <dt>创建</dt>
      <dd>{formatDateTime(run.startedAt)}</dd>
      <dt>目标</dt>
      <dd style={styles.bodyCell}>{run.objective || "未记录"}</dd>
    </dl>
  );
}

function ArtifactDetail({ artifact }: { artifact: ArtifactManifestRow }) {
  return (
    <dl className="detailGrid" style={styles.grid}>
      <dt>产物</dt>
      <dd>{artifact.title}</dd>
      <dt>类型</dt>
      <dd>{artifact.type}</dd>
      <dt>Agent</dt>
      <dd>{artifact.agentId || "未记录"}</dd>
      <dt>任务</dt>
      <dd>{artifact.taskId ? <IdChip value={artifact.taskId} /> : "未关联"}</dd>
      <dt>路径</dt>
      <dd style={styles.bodyCell}>{artifact.path}</dd>
      <dt>摘要</dt>
      <dd style={styles.bodyCell}>{artifact.summary || "未记录"}</dd>
    </dl>
  );
}

function ContextLinks({ message }: { message: BusMessageRow }) {
  const links = [
    message.links.runId ? <IdChip key="run" label="Run" value={message.links.runId} /> : null,
    ...message.links.taskIds.map((id) => <IdChip key={`task-${id}`} label="Task" value={id} />),
    ...message.links.gateIds.map((id) => <IdChip key={`gate-${id}`} label="Gate" value={id} />),
    ...message.links.artifactIds.map((id) => (
      <IdChip key={`artifact-${id}`} label="Artifact" value={id} />
    )),
  ].filter(Boolean);

  return (
    <section style={styles.contextBlock}>
      <strong>关联上下文</strong>
      <div style={styles.linkRow}>{links.length ? links : <span>未关联上下文</span>}</div>
    </section>
  );
}

function MessageTrack({ message }: { message: BusMessageRow }) {
  const delivered = /delivered|acked/i.test(message.deliveryState);
  const acked = /acked/i.test(message.ackState);

  return (
    <section style={styles.track}>
      <strong>消息轨迹</strong>
      <TrackStep label="已发送" active time={formatTime(message.createdAt)} />
      <TrackStep label="已送达" active={delivered} time={delivered ? formatTime(message.updatedAt) : "等待"} />
      <TrackStep label="已读 / 已确认" active={acked} time={acked ? formatTime(message.updatedAt) : "等待"} />
    </section>
  );
}

function TrackStep({ active, label, time }: { active: boolean; label: string; time: string }) {
  return (
    <div style={styles.trackStep}>
      <span style={{ ...styles.trackDot, background: active ? "#16a34a" : "#cbd5e1" }} />
      <span>{label}</span>
      <time>{time}</time>
    </div>
  );
}

function formatDateTime(value: string): string {
  if (!value) {
    return "等待同步";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatTime(value: string): string {
  if (!value) {
    return "等待";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

const styles: Record<string, CSSProperties> = {
  tabs: {
    borderLeft: 0,
    borderRadius: 0,
    borderRight: 0,
    justifyContent: "stretch",
    margin: 0,
    padding: 8,
    width: "100%",
  },
  empty: {
    margin: 12,
  },
  section: {
    display: "grid",
    gap: 12,
    paddingBottom: 12,
  },
  badgeRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    padding: "12px 12px 0",
  },
  grid: {
    display: "grid",
    gap: "10px 12px",
    gridTemplateColumns: "96px minmax(0, 1fr)",
    margin: 0,
    padding: 12,
  },
  bodyCell: {
    overflowWrap: "anywhere",
    whiteSpace: "normal",
  },
  contextBlock: {
    borderTop: "1px solid #e2e8f0",
    display: "grid",
    gap: 9,
    padding: 12,
  },
  linkRow: {
    display: "flex",
    flexWrap: "wrap",
    gap: 7,
  },
  track: {
    borderTop: "1px solid #e2e8f0",
    display: "grid",
    gap: 9,
    padding: 12,
  },
  trackStep: {
    alignItems: "center",
    color: "#475569",
    display: "grid",
    fontSize: 12,
    gap: 8,
    gridTemplateColumns: "14px minmax(0, 1fr) auto",
  },
  trackDot: {
    borderRadius: 999,
    height: 10,
    width: 10,
  },
};
