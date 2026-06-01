import React, { type CSSProperties, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  HelpCircle,
  Send,
  ShieldCheck,
  Upload,
  XCircle,
} from "lucide-react";

import {
  ActionDrawer,
  type ActionDrawerCommand,
  type ActionDrawerItem,
  type ActionDrawerSubmitPayload,
} from "../components/ActionDrawer";
import { IdChip } from "../components/IdChip";
import { Panel } from "../components/Panel";
import { StatusBadge } from "../components/StatusBadge";
import type { EventRow, GateRow, OperationsProjection } from "../operationsApi";
import { sendBusMessage } from "../operationsApi";
import { statusFromState } from "../statusModel";

type GatesPageProps = {
  projection: OperationsProjection;
};

type GateFilter = "waiting" | "all" | "rejected" | "escalated";
type GateDetailTab = "facts" | "timeline" | "decisions";

const filterLabels: Record<GateFilter, string> = {
  waiting: "待审批",
  all: "全部",
  rejected: "已拒绝",
  escalated: "已升级",
};

const actionConfig: Array<{
  command: ActionDrawerCommand;
  label: string;
  description: string;
  icon: typeof CheckCircle2;
  tone: "good" | "bad" | "warn" | "info";
}> = [
  {
    command: "open_gate",
    label: "通过",
    description: "满足门禁要求",
    icon: CheckCircle2,
    tone: "good",
  },
  {
    command: "mark_known",
    label: "驳回",
    description: "不符合门禁要求",
    icon: XCircle,
    tone: "bad",
  },
  {
    command: "request_qa",
    label: "请求补充信息",
    description: "需要更多信息",
    icon: HelpCircle,
    tone: "warn",
  },
  {
    command: "message_controller",
    label: "升级给 QA/Controller",
    description: "转交更高权限决策",
    icon: Upload,
    tone: "info",
  },
];

export function GatesPage({ projection }: GatesPageProps) {
  const [selectedGateId, setSelectedGateId] = useState("");
  const [activeFilter, setActiveFilter] = useState<GateFilter>("waiting");
  const [activeTab, setActiveTab] = useState<GateDetailTab>("facts");
  const [decisionReason, setDecisionReason] = useState("");
  const [drawerItem, setDrawerItem] = useState<ActionDrawerItem | null>(null);
  const [drawerStatus, setDrawerStatus] = useState("");

  const qaOwner = projection.agents.find((agent) => agent.roles.includes("qa"))?.id || "";
  const gates = projection.gates;
  const counts = useMemo(() => buildGateCounts(gates), [gates]);
  const visibleGates = useMemo(
    () => gates.filter((gate) => isGateInFilter(gate, activeFilter)),
    [activeFilter, gates],
  );
  const displayGates = visibleGates.length ? visibleGates : gates;
  const selectedGate =
    gates.find((gate) => gate.id === selectedGateId) ||
    displayGates[0] ||
    gates[0];
  const selectedEvents = selectedGate
    ? projection.events.filter((event) => isGateRelatedEvent(event, selectedGate)).slice(0, 6)
    : [];

  function openDecision(command: ActionDrawerCommand) {
    if (!selectedGate) {
      return;
    }
    const item: ActionDrawerItem = {
      kind: "gate",
      id: selectedGate.id,
      title: selectedGate.name,
      runId: selectedGate.runId,
      taskId: selectedGate.taskId,
      suggestedActions: [command, "message_controller", "request_qa"],
    };
    setDrawerItem(item);
    setDrawerStatus("决策将通过 Agent Bus 发送，不直接改写门禁后端状态。");
  }

  async function submitDrawer(payload: ActionDrawerSubmitPayload) {
    const gate = selectedGate;
    if (!gate) {
      return;
    }
    const recipient = payload.targetAgentId || defaultGateRecipient(gate, qaOwner);
    const prefix = actionLabel(payload.action);
    const reason = decisionReason.trim();
    const text = `${prefix}: ${payload.message}${reason ? `\n决策理由：${reason}` : ""}`;
    try {
      setDrawerStatus("正在通过 Agent Bus 投递门禁决策...");
      await sendBusMessage({
        actor: "operator",
        text,
        recipient_agent_ids: [recipient],
        run_id: gate.runId || undefined,
        task_id: gate.taskId || undefined,
        gate_id: gate.id,
        message_type: "gate_request",
        priority: payload.action === "open_gate" ? "normal" : "high",
      });
      setDrawerStatus("已通过 Agent Bus 投递，等待相关 Agent 响应。");
      setDrawerItem(null);
      setDecisionReason("");
    } catch (error) {
      setDrawerStatus(error instanceof Error ? error.message : "门禁决策投递失败");
    }
  }

  return (
    <section className="gatesPage pageShell">
      <header className="pageHeader">
        <div>
          <h2>审批中心</h2>
          <p>只显示需要决策的门禁，保留风险、事实、时间线和 Agent Bus 决策出口。</p>
        </div>
        <div className="referenceTabs" style={styles.headerTabs}>
          {(Object.keys(filterLabels) as GateFilter[]).map((filter) => (
            <button
              aria-pressed={activeFilter === filter}
              key={filter}
              onClick={() => setActiveFilter(filter)}
              type="button"
            >
              {filterLabels[filter]} {counts[filter]}
            </button>
          ))}
        </div>
      </header>

      <div style={styles.gateWorkspace}>
        <Panel title="审批队列" meta={`共 ${displayGates.length} 项`}>
          <div style={styles.gateList}>
            {displayGates.length ? (
              displayGates.map((gate) => (
                <button
                  aria-pressed={selectedGate?.id === gate.id}
                  className="decisionCard"
                  data-tone={riskTone(gate.risk)}
                  key={gate.id}
                  onClick={() => setSelectedGateId(gate.id)}
                  style={{
                    ...styles.gateCard,
                    ...(selectedGate?.id === gate.id ? styles.selectedBlueBorder : {}),
                  }}
                  type="button"
                >
                  <div style={styles.gateCardHeader}>
                    <strong>{gate.name}</strong>
                    <RiskBadge risk={gate.risk} />
                  </div>
                  <div style={styles.contextChips}>
                    {gate.runId ? <IdChip label="Run" value={gate.runId} /> : null}
                    {gate.taskId ? <IdChip label="Task" value={gate.taskId} /> : null}
                    <IdChip label="Gate" value={gate.id} />
                  </div>
                  <div style={styles.gateFactRow}>
                    <span>负责人 {gate.owner || "未指定"}</span>
                    <span>请求方 {gate.requestedBy || "未记录"}</span>
                    <span>决策人 {gate.decisionBy || "QA · 未决策"}</span>
                  </div>
                  <p style={styles.reasonLine}>{gate.reason || "暂无门禁原因说明"}</p>
                </button>
              ))
            ) : (
              <div className="referenceEmpty" style={styles.empty}>
                <strong>暂无门禁</strong>
                <span>当前投影没有需要审批的门禁记录。</span>
              </div>
            )}
          </div>
        </Panel>

        <section className="panel" style={styles.detailPanel}>
          {selectedGate ? (
            <>
              <header className="panelHeader" style={styles.detailHeader}>
                <div>
                  <h3>{selectedGate.name}</h3>
                  <IdChip value={selectedGate.id} />
                </div>
                <div style={styles.detailHeaderBadges}>
                  <StatusBadge status={statusFromState(selectedGate.state, "gate")} />
                  <RiskBadge risk={selectedGate.risk} />
                </div>
              </header>

              <div style={styles.factStrip}>
                <FactCard label="Run" value={selectedGate.runId} />
                <FactCard label="Task" value={selectedGate.taskId} />
                <FactCard label="负责人" value={selectedGate.owner || "未指定"} />
                <FactCard label="请求方" value={selectedGate.requestedBy || "未记录"} />
                <FactCard label="当前决策人" value={selectedGate.decisionBy || "QA · 未决策"} />
              </div>

              <div className="referenceTabs" style={styles.detailTabs}>
                <button
                  aria-pressed={activeTab === "facts"}
                  onClick={() => setActiveTab("facts")}
                  type="button"
                >
                  门禁详情
                </button>
                <button
                  aria-pressed={activeTab === "timeline"}
                  onClick={() => setActiveTab("timeline")}
                  type="button"
                >
                  时间线
                </button>
                <button
                  aria-pressed={activeTab === "decisions"}
                  onClick={() => setActiveTab("decisions")}
                  type="button"
                >
                  决策记录
                </button>
              </div>

              {activeTab === "facts" ? <GateFacts gate={selectedGate} qaOwner={qaOwner} /> : null}
              {activeTab === "timeline" ? <GateTimeline events={selectedEvents} /> : null}
              {activeTab === "decisions" ? <DecisionHistory gate={selectedGate} events={selectedEvents} /> : null}

              <section style={styles.decisionArea}>
                <label style={styles.decisionReason}>
                  <span>决策理由（建议填写）</span>
                  <textarea
                    onChange={(event) => setDecisionReason(event.target.value)}
                    placeholder="请输入你的决策理由（可选）..."
                    rows={4}
                    value={decisionReason}
                  />
                </label>
                <div style={styles.actionGrid}>
                  {actionConfig.map((action) => {
                    const Icon = action.icon;
                    return (
                      <button
                        className="decisionCard"
                        data-tone={action.tone}
                        key={action.command}
                        onClick={() => openDecision(action.command)}
                        style={styles.actionTile}
                        type="button"
                      >
                        <Icon size={22} strokeWidth={2.3} />
                        <strong>{action.label}</strong>
                        <span>{action.description}</span>
                      </button>
                    );
                  })}
                </div>
                <p style={styles.routeHint}>
                  你的决策将被记录并通过 Agent Bus 通知相关负责人。
                </p>
              </section>
            </>
          ) : (
            <div className="referenceEmpty" style={styles.empty}>
              <strong>等待门禁数据</strong>
              <span>门禁投影为空时不会生成假数据。</span>
            </div>
          )}
        </section>
      </div>

      <ActionDrawer
        agents={projection.agents}
        item={drawerItem}
        onClose={() => setDrawerItem(null)}
        onSubmit={(payload) => void submitDrawer(payload)}
        status={drawerStatus}
      />
    </section>
  );
}

function GateFacts({ gate, qaOwner }: { gate: GateRow; qaOwner: string }) {
  return (
    <div style={styles.detailBody}>
      <section className="referenceCard" style={styles.factPanel}>
        <div className="referenceCardHeader">
          <h3>门禁观察事实</h3>
          <p>来自真实门禁投影</p>
        </div>
        <ul style={styles.factList}>
          <li>
            <CheckCircle2 size={15} strokeWidth={2.3} />
            <span>负责人：{gate.owner || qaOwner || "未指定"}</span>
          </li>
          <li>
            <CheckCircle2 size={15} strokeWidth={2.3} />
            <span>请求方：{gate.requestedBy || "未记录"}</span>
          </li>
          <li>
            <AlertCircle size={15} strokeWidth={2.3} />
            <span>风险等级：{gate.risk || "normal"}</span>
          </li>
          <li>
            <Clock3 size={15} strokeWidth={2.3} />
            <span>状态：{gate.state || "unknown"}</span>
          </li>
        </ul>
      </section>
      <section className="referenceCard" style={styles.factPanel}>
        <div className="referenceCardHeader">
          <h3>关联信息</h3>
          <p>Run / Task / 原因</p>
        </div>
        <dl className="detailGrid" style={styles.detailGrid}>
          <dt>关联 Task</dt>
          <dd>{gate.taskId ? <IdChip value={gate.taskId} /> : "未关联"}</dd>
          <dt>关联 Run</dt>
          <dd>{gate.runId ? <IdChip value={gate.runId} /> : "未关联"}</dd>
          <dt>所属阶段</dt>
          <dd>{gate.state || "未记录"}</dd>
          <dt>原因</dt>
          <dd style={styles.longText}>{gate.reason || "未记录"}</dd>
        </dl>
      </section>
    </div>
  );
}

function GateTimeline({ events }: { events: EventRow[] }) {
  return (
    <div style={styles.timelineList}>
      {events.length ? (
        events.map((event) => (
          <article className="decisionCard" data-tone={event.tone} key={event.id} style={styles.timelineItem}>
            <span style={styles.timelineDot} />
            <div>
              <strong>{event.type}</strong>
              <p>{event.text}</p>
            </div>
            <time>{formatTime(event.time)}</time>
          </article>
        ))
      ) : (
        <div className="referenceEmpty" style={styles.empty}>
          <strong>暂无时间线事件</strong>
          <span>没有匹配该门禁、Run 或 Task 的事件记录。</span>
        </div>
      )}
    </div>
  );
}

function DecisionHistory({ gate, events }: { gate: GateRow; events: EventRow[] }) {
  const decisionEvents = events.filter((event) => /gate|decision|approve|reject|qa/i.test(event.type));

  return (
    <div style={styles.timelineList}>
      <article className="referenceCard" style={styles.decisionSummary}>
        <strong>当前决策</strong>
        <span>{gate.decisionBy ? `${gate.decisionBy} 已记录` : "尚未记录最终决策"}</span>
      </article>
      {decisionEvents.map((event) => (
        <article className="decisionCard" data-tone={event.tone} key={event.id} style={styles.timelineItem}>
          <span style={styles.timelineDot} />
          <div>
            <strong>{event.source}</strong>
            <p>{event.text}</p>
          </div>
          <time>{formatTime(event.time)}</time>
        </article>
      ))}
      {!decisionEvents.length ? (
        <div className="referenceEmpty" style={styles.empty}>
          <strong>暂无历史决策</strong>
          <span>使用下方动作按钮通过 Agent Bus 发起决策记录。</span>
        </div>
      ) : null}
    </div>
  );
}

function FactCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={styles.factCard}>
      <span>{label}</span>
      <strong>{value ? <IdChip value={value} /> : "未记录"}</strong>
    </div>
  );
}

function RiskBadge({ risk }: { risk: string }) {
  const tone = riskTone(risk);
  const label = risk || "normal";
  const color =
    tone === "bad" ? "#dc2626" : tone === "warn" ? "#d97706" : tone === "good" ? "#16a34a" : "#2563eb";
  return <span style={{ ...styles.riskBadge, color }}>{riskLabel(label)}</span>;
}

function buildGateCounts(gates: GateRow[]): Record<GateFilter, number> {
  return {
    all: gates.length,
    waiting: gates.filter((gate) => isGateWaiting(gate)).length,
    rejected: gates.filter((gate) => /reject|fail|denied/i.test(gate.state)).length,
    escalated: gates.filter((gate) => /escalat|qa|review/i.test(`${gate.state} ${gate.reason}`)).length,
  };
}

function isGateInFilter(gate: GateRow, filter: GateFilter): boolean {
  if (filter === "all") {
    return true;
  }
  if (filter === "waiting") {
    return isGateWaiting(gate);
  }
  if (filter === "rejected") {
    return /reject|fail|denied/i.test(gate.state);
  }
  return /escalat|qa|review/i.test(`${gate.state} ${gate.reason}`);
}

function isGateWaiting(gate: GateRow): boolean {
  const status = statusFromState(gate.state, "gate");
  return status.isActionRequired || /open|wait|pending|review|gate/i.test(gate.state);
}

function isGateRelatedEvent(event: EventRow, gate: GateRow): boolean {
  return Boolean(
    event.runId === gate.runId ||
      event.taskId === gate.taskId ||
      event.text.includes(gate.id) ||
      event.text.includes(gate.name),
  );
}

function defaultGateRecipient(gate: GateRow, qaOwner: string): string {
  return gate.owner || gate.requestedBy || qaOwner || "controller";
}

function actionLabel(action: ActionDrawerCommand): string {
  if (action === "open_gate") {
    return "门禁通过请求";
  }
  if (action === "request_qa") {
    return "请求补充信息";
  }
  if (action === "message_controller") {
    return "升级给 QA/Controller";
  }
  if (action === "mark_known") {
    return "门禁驳回记录";
  }
  return "门禁动作";
}

function riskTone(risk: string): "good" | "bad" | "warn" | "info" {
  const value = risk.toLowerCase();
  if (/high|critical|red|danger|blocked|risk/.test(value)) {
    return "bad";
  }
  if (/medium|warn|pending|unknown/.test(value)) {
    return "warn";
  }
  if (/low|green|safe/.test(value)) {
    return "good";
  }
  return "info";
}

function riskLabel(risk: string): string {
  const value = risk.toLowerCase();
  if (/high|critical|red|danger/.test(value)) {
    return "高风险";
  }
  if (/medium|warn/.test(value)) {
    return "中风险";
  }
  if (/low|green|safe/.test(value)) {
    return "低风险";
  }
  return risk;
}

function formatTime(value: string): string {
  if (!value) {
    return "等待同步";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const styles: Record<string, CSSProperties> = {
  headerTabs: {
    justifyContent: "flex-end",
  },
  gateWorkspace: {
    alignItems: "start",
    display: "grid",
    gap: 16,
    gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 360px), 1fr))",
    minWidth: 0,
  },
  gateList: {
    display: "grid",
    gap: 10,
    maxHeight: "min(68vh, 760px)",
    overflow: "auto",
    padding: 12,
  },
  gateCard: {
    background: "#ffffff",
    minHeight: 148,
    padding: 14,
  },
  selectedBlueBorder: {
    borderColor: "#2563eb",
    boxShadow: "inset 3px 0 0 #2563eb",
  },
  gateCardHeader: {
    alignItems: "flex-start",
    display: "flex",
    gap: 10,
    justifyContent: "space-between",
  },
  contextChips: {
    display: "flex",
    flexWrap: "wrap",
    gap: 7,
  },
  gateFactRow: {
    color: "#475569",
    display: "grid",
    gap: 8,
    gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 150px), 1fr))",
    fontSize: 12,
  },
  reasonLine: {
    color: "#334155",
    fontSize: 12,
    lineHeight: 1.5,
    margin: 0,
  },
  detailPanel: {
    minWidth: 0,
  },
  detailHeader: {
    alignItems: "flex-start",
  },
  detailHeaderBadges: {
    alignItems: "center",
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    justifyContent: "flex-end",
  },
  factStrip: {
    borderBottom: "1px solid #e2e8f0",
    display: "grid",
    gap: 10,
    gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 138px), 1fr))",
    padding: 12,
  },
  factCard: {
    border: "1px solid #e2e8f0",
    borderRadius: 8,
    display: "grid",
    gap: 7,
    minHeight: 58,
    padding: 10,
  },
  detailTabs: {
    borderLeft: 0,
    borderRadius: 0,
    borderRight: 0,
    padding: 8,
  },
  detailBody: {
    display: "grid",
    gap: 12,
    gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))",
    padding: 12,
  },
  factPanel: {
    boxShadow: "none",
  },
  factList: {
    display: "grid",
    gap: 10,
    listStyle: "none",
    margin: 0,
    padding: 14,
  },
  detailGrid: {
    display: "grid",
    gap: "10px 12px",
    gridTemplateColumns: "96px minmax(0, 1fr)",
    margin: 0,
    padding: 14,
  },
  longText: {
    overflowWrap: "anywhere",
    whiteSpace: "normal",
  },
  timelineList: {
    display: "grid",
    gap: 10,
    padding: 12,
  },
  timelineItem: {
    alignItems: "center",
    gridTemplateColumns: "12px minmax(0, 1fr) auto",
  },
  timelineDot: {
    background: "#2563eb",
    borderRadius: 999,
    height: 8,
    width: 8,
  },
  decisionSummary: {
    display: "flex",
    justifyContent: "space-between",
    padding: 12,
  },
  decisionArea: {
    borderTop: "1px solid #e2e8f0",
    display: "grid",
    gap: 12,
    padding: 12,
  },
  decisionReason: {
    display: "grid",
    gap: 7,
  },
  actionGrid: {
    display: "grid",
    gap: 10,
    gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 160px), 1fr))",
  },
  actionTile: {
    alignContent: "center",
    justifyItems: "start",
    minHeight: 76,
  },
  routeHint: {
    color: "#64748b",
    fontSize: 12,
    margin: 0,
  },
  riskBadge: {
    alignItems: "center",
    border: "1px solid currentColor",
    borderRadius: 999,
    display: "inline-flex",
    fontSize: 12,
    fontWeight: 850,
    lineHeight: 1,
    padding: "5px 9px",
    whiteSpace: "nowrap",
  },
  empty: {
    margin: 12,
  },
};
