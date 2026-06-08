import React, { type CSSProperties, type FormEvent } from "react";
import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  MessageSquare,
  Plus,
  RefreshCw,
  Search,
  Send,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { AgentMark } from "../components/AgentMark";
import { DetailRail } from "../components/DetailRail";
import { IdChip } from "../components/IdChip";
import { Panel } from "../components/Panel";
import { StatusBadge } from "../components/StatusBadge";
import type { AgentRow, BusMessageRow, OperationsProjection, UiAgentSummary } from "../operationsApi";
import { fetchBusMessages, sendBusMessage } from "../operationsApi";
import { statusFromState } from "../statusModel";

type CommunicationPageProps = {
  projection: OperationsProjection;
};

type MessageType = "instruction" | "status" | "question" | "request_qa";
type Priority = "normal" | "high";
type MessageFilter = "all" | "sent" | "mine" | "followed";
type SpaceKey = "urgent" | "daily" | "release" | "cost";

const spaceDefinitions: Array<{
  key: SpaceKey;
  label: string;
  description: string;
  icon: typeof AlertTriangle;
  tone: "bad" | "info" | "good" | "warn";
}> = [
  {
    key: "urgent",
    label: "紧急异常",
    description: "阻塞、失败、高优先级",
    icon: AlertTriangle,
    tone: "bad",
  },
  {
    key: "daily",
    label: "日常协作",
    description: "任务同步与交接",
    icon: Bell,
    tone: "info",
  },
  {
    key: "release",
    label: "发布变更",
    description: "门禁、产物、变更",
    icon: CheckCircle2,
    tone: "good",
  },
  {
    key: "cost",
    label: "成本优化",
    description: "压缩、替换、效率",
    icon: MessageSquare,
    tone: "warn",
  },
];

const filterLabels: Record<MessageFilter, string> = {
  all: "全部",
  sent: "仅我发送",
  mine: "@ 我的",
  followed: "关注的 Agent",
};

const messageTypeLabels: Record<string, string> = {
  instruction: "指令",
  status: "状态",
  question: "问题",
  request: "请求",
  request_qa: "请求 QA",
  gate_request: "门禁请求",
  verification_result: "验证结果",
  handoff: "交接",
};

export function CommunicationPage({ projection }: CommunicationPageProps) {
  const [messages, setMessages] = useState<BusMessageRow[]>([]);
  const [selectedMessageId, setSelectedMessageId] = useState("");
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [selectedRecipients, setSelectedRecipients] = useState<string[]>([]);
  const [messageText, setMessageText] = useState("");
  const [messageType, setMessageType] = useState<MessageType>("instruction");
  const [priority, setPriority] = useState<Priority>("normal");
  const [status, setStatus] = useState("");
  const [activeFilter, setActiveFilter] = useState<MessageFilter>("all");
  const [activeSpace, setActiveSpace] = useState<SpaceKey>("daily");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [query, setQuery] = useState("");

  const rawAgentById = useMemo(
    () => new Map(projection.agents.map((agent) => [agent.id, agent])),
    [projection.agents],
  );
  const visibleAgents = useMemo(
    () =>
      projection.ui.visibleAgents.filter(
        (agent) => agent.uiVisibilityState === "main" || agent.uiVisibilityState === "needs_attention",
      ),
    [projection.ui.visibleAgents],
  );
  const archivedAgents = projection.ui.archivedAgents;
  const agentById = useMemo(
    () =>
      new Map(
        [...visibleAgents, ...archivedAgents].map((agent) => [
          agent.agentId,
          agentSummaryToAgentRow(agent, rawAgentById.get(agent.agentId)),
        ]),
      ),
    [archivedAgents, rawAgentById, visibleAgents],
  );
  const operatorAgentIds = useMemo(
    () =>
      projection.agents
        .filter((agent) => /controller|operator/i.test(`${agent.role} ${agent.roles.join(" ")}`))
        .map((agent) => agent.id),
    [projection.agents],
  );
  const spaceCounts = useMemo(() => buildSpaceCounts(messages), [messages]);
  const filteredMessages = useMemo(
    () =>
      messages.filter((message) =>
        isMessageInView(message, {
          activeFilter,
          activeSpace,
          operatorAgentIds,
          query,
          selectedAgentId,
          unreadOnly,
        }),
      ),
    [activeFilter, activeSpace, messages, operatorAgentIds, query, selectedAgentId, unreadOnly],
  );
  const selectedMessage =
    filteredMessages.find((message) => message.messageId === selectedMessageId) ||
    filteredMessages[0];
  const selectedAgent =
    agentById.get(selectedAgentId) ||
    selectedMessage?.recipientAgentIds.map((id) => agentById.get(id)).find(Boolean) ||
    (visibleAgents[0]
      ? agentSummaryToAgentRow(visibleAgents[0], rawAgentById.get(visibleAgents[0].agentId))
      : undefined) ||
    projection.agents[0];

  useEffect(() => {
    const controller = new AbortController();
    void loadMessages(controller.signal);
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!filteredMessages.length) {
      if (selectedMessageId) {
        setSelectedMessageId("");
      }
      return;
    }
    if (
      (!selectedMessageId ||
        !filteredMessages.some((message) => message.messageId === selectedMessageId))
    ) {
      setSelectedMessageId(filteredMessages[0].messageId);
    }
  }, [filteredMessages, selectedMessageId]);

  async function loadMessages(signal?: AbortSignal) {
    try {
      const nextMessages = await fetchBusMessages(signal);
      setMessages(nextMessages);
      setStatus(`已同步 ${nextMessages.length} 条消息`);
      if (!selectedMessageId && nextMessages[0]) {
        setSelectedMessageId(nextMessages[0].messageId);
      }
    } catch (error) {
      if (!signal?.aborted) {
        setStatus(error instanceof Error ? error.message : "消息投影同步失败");
      }
    }
  }

  function selectAgent(agent: UiAgentSummary) {
    setSelectedAgentId(agent.agentId);
    setSelectedRecipients((current) => {
      if (current.includes(agent.agentId)) {
        return current;
      }
      return [agent.agentId];
    });
  }

  function selectRecipient(value: string) {
    if (value === "active") {
      const activeAgents = visibleAgents
        .filter((agent) => /assigned|working|waiting|blocked|claim_pending/i.test(agent.workloadState))
        .map((agent) => agent.agentId);
      setSelectedRecipients(
        activeAgents.length ? activeAgents : visibleAgents.slice(0, 2).map((agent) => agent.agentId),
      );
      return;
    }
    if (value === "selected") {
      return;
    }
    if (value) {
      setSelectedRecipients([value]);
      setSelectedAgentId(value);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = messageText.trim();
    if (!text) {
      setStatus("请输入要发送的指令内容。");
      return;
    }
    if (selectedRecipients.length === 0) {
      setStatus("请选择至少一个收件 Agent。");
      return;
    }
    try {
      setStatus("正在通过 Agent Bus 发送...");
      await sendBusMessage({
        actor: "operator",
        text,
        recipient_agent_ids: selectedRecipients,
        message_type: messageType,
        priority,
      });
      setMessageText("");
      await loadMessages();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "发送失败");
    }
  }

  const selectedRecipientValue =
    selectedRecipients.length === 1 ? selectedRecipients[0] : selectedRecipients.length ? "selected" : "";

  return (
    <section className="communicationPage pageShell">
      <header className="pageHeader">
        <div>
          <h2>通信</h2>
          <p>在通信空间中与 Agent 协作，发送指令、请求验证并跟踪执行反馈。</p>
        </div>
        <button className="toolbarButton" onClick={() => void loadMessages()} type="button">
          <RefreshCw size={14} strokeWidth={2.2} />
          刷新消息
        </button>
      </header>

      <div style={styles.communicationGrid}>
        <aside style={styles.leftRail}>
          <Panel title="通信空间" meta={`${messages.length} 条消息`}>
            <div style={styles.spaceList}>
              {spaceDefinitions.map((space) => {
                const Icon = space.icon;
                return (
                  <button
                    aria-pressed={activeSpace === space.key}
                    className="decisionCard"
                    data-tone={space.tone}
                    key={space.key}
                    onClick={() => setActiveSpace(space.key)}
                    style={{
                      ...styles.spaceButton,
                      ...(activeSpace === space.key ? styles.selectedBlueBorder : {}),
                    }}
                    type="button"
                  >
                    <span style={styles.iconBadge} data-tone={space.tone}>
                      <Icon size={15} strokeWidth={2.4} />
                    </span>
                    <span style={styles.spaceCopy}>
                      <strong>{space.label}</strong>
                      <small>{space.description}</small>
                    </span>
                    <span style={styles.countText}>{spaceCounts[space.key]} 未读</span>
                  </button>
                );
              })}
            </div>
          </Panel>

          <Panel title="Agent 列表" meta={`${visibleAgents.length} active / ${archivedAgents.length} archived`}>
            <div style={styles.agentList}>
              {visibleAgents.length ? (
                visibleAgents.map((agent) => (
                  <button
                    aria-pressed={selectedAgentId === agent.agentId || selectedRecipients.includes(agent.agentId)}
                    className="gateItem"
                    key={agent.agentId}
                    onClick={() => selectAgent(agent)}
                    style={{
                      ...styles.agentButton,
                      ...(selectedAgentId === agent.agentId ? styles.selectedBlueBorder : {}),
                    }}
                    type="button"
                  >
                    <AgentMark agent={agentSummaryToAgentRow(agent, rawAgentById.get(agent.agentId))} compact />
                    <span style={styles.agentMeta}>
                      <span title={agent.runtimeState || undefined}>{agentHealthLabel(agent)}</span>
                      <strong>{agent.queuedInbox} inbox</strong>
                    </span>
                  </button>
                ))
              ) : (
                <p className="referenceEmpty" style={styles.emptyNoMargin}>
                  当前没有可选 Agent。
                </p>
              )}
              {archivedAgents.length ? (
                <details className="agentArchiveFold">
                  <summary>Archived Agents ({archivedAgents.length})</summary>
                  {archivedAgents.map((agent) => (
                    <button
                      aria-pressed={selectedAgentId === agent.agentId || selectedRecipients.includes(agent.agentId)}
                      className="gateItem"
                      key={agent.agentId}
                      onClick={() => selectAgent(agent)}
                      style={{
                        ...styles.agentButton,
                        ...(selectedAgentId === agent.agentId ? styles.selectedBlueBorder : {}),
                      }}
                      type="button"
                    >
                      <AgentMark agent={agentSummaryToAgentRow(agent, rawAgentById.get(agent.agentId))} compact />
                      <span style={styles.agentMeta}>
                        <span title={agent.hiddenReason || agent.runtimeState || undefined}>{agentHealthLabel(agent)}</span>
                        <strong>{agent.queuedInbox} inbox</strong>
                      </span>
                    </button>
                  ))}
                </details>
              ) : null}
            </div>
          </Panel>
        </aside>

        <main style={styles.messageColumn}>
          <Panel title="消息流" meta={status || "Bus-backed"}>
            <div style={styles.filterBar}>
              <span style={styles.filterLabel}>范围</span>
              <div className="referenceTabs communicationFilterTabs" aria-label="消息范围">
                {(Object.keys(filterLabels) as MessageFilter[]).map((filter) => (
                  <button
                    aria-pressed={activeFilter === filter}
                    key={filter}
                    onClick={() => setActiveFilter(filter)}
                    type="button"
                  >
                    {filterLabels[filter]}
                  </button>
                ))}
              </div>
              <label style={styles.unreadToggle}>
                <input
                  checked={unreadOnly}
                  onChange={(event) => setUnreadOnly(event.target.checked)}
                  type="checkbox"
                />
                仅未读
              </label>
              <label style={styles.searchBox}>
                <Search size={14} strokeWidth={2.2} />
                <input
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="搜索消息、Agent、Run、Gate..."
                  type="search"
                  value={query}
                />
              </label>
            </div>

            <div className="communicationMessageList" style={styles.messageList}>
              {filteredMessages.length ? (
                filteredMessages.map((message) => (
                  <button
                    aria-pressed={message.messageId === selectedMessage?.messageId}
                    className="decisionCard communicationMessageCard"
                    data-tone={message.priority === "high" ? "bad" : message.replyState === "waiting_reply" ? "warn" : "info"}
                    key={message.messageId}
                    onClick={() => {
                      setSelectedMessageId(message.messageId);
                      const firstRecipient = message.recipientAgentIds[0];
                      if (firstRecipient) {
                        setSelectedAgentId(firstRecipient);
                      }
                    }}
                    style={{
                      ...styles.messageCard,
                      ...(message.messageId === selectedMessage?.messageId
                        ? styles.selectedBlueBorder
                        : {}),
                    }}
                    type="button"
                  >
                    <div style={styles.messageHeader}>
                      <div style={styles.senderLine}>
                        <AgentInitial label={message.senderName} />
                        <strong>{message.senderName || message.senderAgentId || "system"}</strong>
                        <span>→</span>
                        <strong>{recipientSummary(message, agentById)}</strong>
                        <span style={styles.messageType}>{messageTypeLabel(message.messageType)}</span>
                      </div>
                      <div style={styles.messageState}>
                        <StatusBadge status={statusFromState(message.deliveryState, "message")} />
                        <time>{formatTime(message.createdAt)}</time>
                      </div>
                    </div>
                    <p style={styles.messageBody}>{message.body || "无消息正文"}</p>
                    <div style={styles.contextChips}>
                      {message.links.runId ? <IdChip label="Run" value={message.links.runId} /> : null}
                      {message.links.taskIds.slice(0, 2).map((taskId) => (
                        <IdChip key={taskId} label="Task" value={taskId} />
                      ))}
                      {message.links.gateIds.slice(0, 1).map((gateId) => (
                        <IdChip key={gateId} label="Gate" value={gateId} />
                      ))}
                      {message.links.artifactIds.slice(0, 1).map((artifactId) => (
                        <IdChip key={artifactId} label="Artifact" value={artifactId} />
                      ))}
                    </div>
                  </button>
                ))
              ) : (
                <div className="referenceEmpty" style={styles.emptyNoMargin}>
                  <strong>没有匹配的消息</strong>
                  <span>
                    {activeFilter === "followed" && !selectedAgentId
                      ? "请选择左侧 Agent 后查看关注消息。"
                      : "调整筛选条件，或通过底部发送区向 Agent 发起一次协作。"}
                  </span>
                </div>
              )}
            </div>

            <form onSubmit={submit} style={styles.composer}>
              <div style={styles.composerRow}>
                <label style={styles.composerField}>
                  <span>收件人</span>
                  <select
                    onChange={(event) => selectRecipient(event.target.value)}
                    value={selectedRecipientValue}
                  >
                    <option value="">选择 Agent</option>
                    <option value="selected">已选择 {selectedRecipients.length} 个 Agent</option>
                    <option value="active">运行中的 Agent</option>
                    {visibleAgents.map((agent) => (
                      <option key={agent.agentId} value={agent.agentId}>
                        {agent.displayName || agent.agentId}
                      </option>
                    ))}
                  </select>
                </label>
                <label style={styles.composerField}>
                  <span>消息类型</span>
                  <select
                    onChange={(event) => setMessageType(event.target.value as MessageType)}
                    value={messageType}
                  >
                    <option value="instruction">指令 instruction</option>
                    <option value="question">问题 question</option>
                    <option value="request_qa">请求 QA</option>
                    <option value="status">状态 status</option>
                  </select>
                </label>
                <label style={styles.composerField}>
                  <span>优先级</span>
                  <select
                    onChange={(event) => setPriority(event.target.value as Priority)}
                    value={priority}
                  >
                    <option value="normal">普通</option>
                    <option value="high">高优先级</option>
                  </select>
                </label>
              </div>
              <div style={styles.composerTextRow}>
                <input
                  onChange={(event) => setMessageText(event.target.value)}
                  placeholder="输入指令内容，支持 @ Agent 或引用上下文..."
                  value={messageText}
                />
                <button className="commandButton" style={styles.primaryButton} type="submit">
                  <Send size={14} strokeWidth={2.2} />
                  通过 Agent Bus 发送
                </button>
              </div>
            </form>
          </Panel>
        </main>

        <aside style={styles.rightRail}>
          <button
            className="commandButton"
            onClick={() => {
              const firstRecipient = selectedAgent?.id || visibleAgents[0]?.agentId;
              if (firstRecipient) {
                setSelectedRecipients([firstRecipient]);
                setSelectedAgentId(firstRecipient);
              }
              setMessageType("instruction");
            }}
            style={{ ...styles.primaryButton, width: "100%" }}
            type="button"
          >
            <Send size={15} strokeWidth={2.3} />
            发送指令
          </button>
          <DetailRail
            agent={selectedAgent}
            message={selectedMessage}
            title={selectedMessage ? "消息详情" : "Agent 详情"}
          />
        </aside>
      </div>
    </section>
  );
}

function isMessageInView(
  message: BusMessageRow,
  options: {
    activeFilter: MessageFilter;
    activeSpace: SpaceKey;
    operatorAgentIds: string[];
    query: string;
    selectedAgentId: string;
    unreadOnly: boolean;
  },
): boolean {
  if (classifyMessageSpace(message) !== options.activeSpace) {
    return false;
  }
  if (options.unreadOnly && /acked|delivered|not_required/i.test(message.ackState)) {
    return false;
  }
  if (
    options.activeFilter === "sent" &&
    !isOperatorLikeIdentity(`${message.senderName} ${message.senderAgentId}`) &&
    !options.operatorAgentIds.includes(message.senderAgentId)
  ) {
    return false;
  }
  if (
    options.activeFilter === "mine" &&
    !message.recipientAgentIds.some(
      (id) => options.operatorAgentIds.includes(id) || isOperatorLikeIdentity(id),
    )
  ) {
    return false;
  }
  if (
    options.activeFilter === "followed" &&
    !options.selectedAgentId
  ) {
    return false;
  }
  if (
    options.activeFilter === "followed" &&
    ![message.senderAgentId, ...message.recipientAgentIds].includes(options.selectedAgentId)
  ) {
    return false;
  }
  const query = options.query.trim().toLowerCase();
  if (!query) {
    return true;
  }
  const haystack = [
    message.body,
    message.senderName,
    message.senderAgentId,
    message.messageType,
    message.spaceId,
    message.threadId,
    ...message.recipientAgentIds,
    message.links.runId || "",
    ...message.links.taskIds,
    ...message.links.gateIds,
    ...message.links.artifactIds,
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function isOperatorLikeIdentity(value: string | undefined): boolean {
  return /operator|controller/i.test(value || "");
}

function agentSummaryToAgentRow(summary: UiAgentSummary, fallback?: AgentRow): AgentRow {
  const role = summary.role || fallback?.role || "worker";
  return {
    id: summary.agentId || fallback?.id || "unknown-agent",
    name: summary.displayName || fallback?.name || summary.agentId || "unknown-agent",
    role,
    roles: fallback?.roles?.length ? fallback.roles : role ? [role] : [],
    sessionId: fallback?.sessionId || "no-session",
    state: summary.runtimeState || summary.presenceState || fallback?.state || "unknown",
    inboxCount: summary.queuedInbox,
    capabilities: fallback?.capabilities || [],
  };
}

function agentHealthLabel(agent: UiAgentSummary): string {
  if (agent.uiVisibilityState === "needs_attention") {
    return "Needs attention";
  }
  const labels: Record<string, string> = {
    offline: "Offline",
    online: "Online",
    stale: "Stale",
  };
  return labels[agent.presenceState] || agent.presenceState || "Unknown";
}

function classifyMessageSpace(message: BusMessageRow): SpaceKey {
  const explicitSpace = normalizeSpaceKey(message.spaceId);
  if (explicitSpace) {
    return explicitSpace;
  }

  const priority = message.priority.toLowerCase();
  const messageType = message.messageType.toLowerCase();
  const delivery = `${message.deliveryState} ${message.ackState} ${message.replyState}`.toLowerCase();
  const linkedChange =
    message.links.gateIds.length > 0 || message.links.artifactIds.length > 0;

  if (
    priority === "high" ||
    /interrupt|blocked|failed|reject|stuck|fencing|violation/.test(messageType) ||
    /waiting_reply|failed|blocked|reject/.test(delivery)
  ) {
    return "urgent";
  }
  if (
    linkedChange ||
    /gate|artifact|release|change|ready|pass|verification|review/.test(messageType)
  ) {
    return "release";
  }
  if (/cost|optimi[sz]e|compress|budget|token/.test(messageType)) {
    return "cost";
  }
  const text = `${message.body} ${message.threadId}`.toLowerCase();
  if (/high|urgent|fail|error|block|reject|stuck|interrupt/.test(text)) {
    return "urgent";
  }
  if (/gate|artifact|release|change|ready|pass|verification/.test(text)) {
    return "release";
  }
  if (/cost|optimi[sz]e|compress|budget|token/.test(text)) {
    return "cost";
  }
  return "daily";
}

function normalizeSpaceKey(value: string): SpaceKey | null {
  const normalized = value.toLowerCase().replace(/[_\s-]+/g, "");
  if (["urgent", "incident", "blocker", "critical"].includes(normalized)) {
    return "urgent";
  }
  if (["daily", "runtime", "coordination", "default"].includes(normalized)) {
    return "daily";
  }
  if (["release", "gate", "artifact", "change"].includes(normalized)) {
    return "release";
  }
  if (["cost", "budget", "token", "efficiency"].includes(normalized)) {
    return "cost";
  }
  return null;
}

function buildSpaceCounts(messages: BusMessageRow[]): Record<SpaceKey, number> {
  return messages.reduce<Record<SpaceKey, number>>(
    (counts, message) => {
      if (!/acked|delivered|not_required/i.test(message.ackState)) {
        counts[classifyMessageSpace(message)] += 1;
      }
      return counts;
    },
    { urgent: 0, daily: 0, release: 0, cost: 0 },
  );
}

function recipientSummary(message: BusMessageRow, agentById: Map<string, AgentRow>): string {
  if (!message.recipientAgentIds.length) {
    return "广播";
  }
  return message.recipientAgentIds
    .slice(0, 2)
    .map((id) => agentById.get(id)?.name || id)
    .join(", ");
}

function messageTypeLabel(type: string): string {
  return messageTypeLabels[type] || type || "消息";
}

function formatTime(value: string): string {
  if (!value) {
    return "等待同步";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function AgentInitial({ label }: { label: string }) {
  const initial = label
    .split(/[-_\s]/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return <span style={styles.agentInitial}>{initial || "AB"}</span>;
}

const styles: Record<string, CSSProperties> = {
  communicationGrid: {
    alignItems: "start",
    display: "grid",
    gap: 16,
    gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 300px), 1fr))",
    minWidth: 0,
  },
  leftRail: {
    display: "grid",
    gap: 14,
    minWidth: 0,
  },
  rightRail: {
    display: "grid",
    gap: 12,
    minWidth: 0,
  },
  messageColumn: {
    minWidth: 0,
  },
  spaceList: {
    display: "grid",
    gap: 8,
    padding: 10,
  },
  spaceButton: {
    alignItems: "center",
    gridTemplateColumns: "32px minmax(0, 1fr) auto",
    minHeight: 56,
  },
  selectedBlueBorder: {
    borderColor: "#2563eb",
    boxShadow: "inset 3px 0 0 #2563eb",
  },
  iconBadge: {
    alignItems: "center",
    border: "1px solid #dbeafe",
    borderRadius: 8,
    color: "#2563eb",
    display: "inline-flex",
    height: 28,
    justifyContent: "center",
    width: 28,
  },
  spaceCopy: {
    display: "grid",
    gap: 3,
    minWidth: 0,
  },
  countText: {
    color: "#2563eb",
    fontSize: 12,
    fontWeight: 800,
    whiteSpace: "nowrap",
  },
  agentList: {
    display: "grid",
    gap: 8,
    maxHeight: 438,
    overflow: "auto",
    padding: 10,
  },
  agentButton: {
    alignItems: "center",
    background: "#ffffff",
    border: "1px solid #e2e8f0",
    borderRadius: 8,
    cursor: "pointer",
    gridTemplateColumns: "minmax(0, 1fr)",
    minHeight: 62,
  },
  agentMeta: {
    alignItems: "center",
    color: "#64748b",
    display: "flex",
    fontSize: 12,
    gap: 12,
    justifyContent: "space-between",
  },
  filterBar: {
    alignItems: "center",
    borderBottom: "1px solid #e2e8f0",
    display: "flex",
    flexWrap: "wrap",
    gap: 10,
    padding: 12,
  },
  filterLabel: {
    color: "#64748b",
    fontSize: 12,
    fontWeight: 800,
  },
  unreadToggle: {
    alignItems: "center",
    color: "#475569",
    display: "inline-flex",
    gap: 6,
    fontSize: 12,
    fontWeight: 800,
  },
  searchBox: {
    alignItems: "center",
    border: "1px solid #e2e8f0",
    borderRadius: 8,
    color: "#64748b",
    display: "inline-flex",
    flex: "1 1 230px",
    gap: 8,
    minHeight: 36,
    padding: "0 10px",
  },
  messageList: {
    display: "grid",
    gap: 10,
    maxHeight: "min(54vh, 610px)",
    minHeight: 360,
    overflow: "auto",
    padding: 12,
  },
  messageCard: {
    background: "#ffffff",
    minHeight: 108,
    padding: 14,
  },
  messageHeader: {
    alignItems: "flex-start",
    display: "flex",
    gap: 10,
    justifyContent: "space-between",
  },
  senderLine: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    minWidth: 0,
  },
  agentInitial: {
    alignItems: "center",
    background: "#2563eb",
    borderRadius: 8,
    color: "#ffffff",
    display: "inline-flex",
    fontSize: 12,
    fontWeight: 850,
    height: 28,
    justifyContent: "center",
    width: 28,
  },
  messageType: {
    border: "1px solid #bfdbfe",
    borderRadius: 6,
    background: "#eff6ff",
    color: "#2563eb",
    fontSize: 12,
    fontWeight: 800,
    padding: "3px 7px",
  },
  messageState: {
    alignItems: "center",
    display: "flex",
    gap: 8,
  },
  messageBody: {
    color: "#334155",
    fontSize: 13,
    lineHeight: 1.55,
    margin: 0,
  },
  contextChips: {
    display: "flex",
    flexWrap: "wrap",
    gap: 7,
  },
  composer: {
    borderTop: "1px solid #e2e8f0",
    display: "grid",
    gap: 10,
    padding: 12,
  },
  composerRow: {
    display: "grid",
    gap: 10,
    gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 160px), 1fr))",
  },
  composerTextRow: {
    display: "grid",
    gap: 10,
    gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 240px), 1fr))",
  },
  composerField: {
    color: "#64748b",
    display: "grid",
    fontSize: 12,
    fontWeight: 800,
    gap: 5,
  },
  primaryButton: {
    background: "#2563eb",
    color: "#ffffff",
  },
  emptyNoMargin: {
    margin: 0,
  },
};
