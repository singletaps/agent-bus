import type { Tone, ViewName } from "./operationsApi";

export const viewLabels = {
  Home: "控制首页",
  Communication: "通信",
  Runs: "任务流",
  Gates: "门禁",
  Artifacts: "产物",
  Diagnostics: "诊断",
  Settings: "设置",
} as Record<ViewName, string>;

export const uiText = {
  appTitle: "Agent Bus",
  appSubtitle: "运行控制台",
  roomEyebrow: "AGENT OPERATIONS ROOM",
  roomTitle: "运行态势",
  refresh: "刷新",
  metrics: {
    agents: "Agent",
    pendingInbox: "待处理 inbox",
    openGates: "开放门禁",
    contextFaults: "上下文风险",
    currentRun: "当前任务流",
  },
  brief: {
    primaryAction: "优先动作",
    handleIncident: "处理异常任务",
    activeRun: "当前任务流",
  },
  workstation: {
    currentWork: "当前",
    nextAction: "下一步",
    trust: "状态依据",
  },
  panels: {
    runtimePosture: "当前运行态势",
    workflowMap: "任务流地图",
    actionQueue: "行动队列",
    communication: "通信台",
    agentDetail: "Agent 详情",
    messageDetail: "消息详情",
    runs: "任务流",
    gates: "审批中心",
    artifacts: "产物",
    diagnostics: "诊断",
    settings: "设置",
    agentDock: "Agent 工作台",
    missionSurface: "任务态势",
    inspector: "上下文详情",
    eventConsole: "诊断事件",
    replacementDock: "接管候选",
    commandComposer: "Bus 中断指令",
    runGraph: "任务流列表",
  },
  taskLanes: {
    active: "执行中",
    attention: "需处理",
    backlog: "待排队",
  },
  decisionLanes: {
    needsAction: "需处理",
    active: "进行中",
    waitingGate: "等待门禁",
    waiting: "等待",
    review: "审核中",
    done: "已完成",
  },
  gateTabs: {
    open: "开放",
    high: "高风险",
    handled: "已处理",
    all: "全部",
  },
  inspectorTabs: {
    overview: "概览",
    context: "上下文",
    events: "事件",
    actions: "操作",
  },
  eventFilters: {
    all: "全部",
    gate: "门禁",
    interrupt: "中断",
    replacement: "接管",
    error: "异常",
  },
  emptyStates: {
    inspector:
      "选择一个 Agent、任务、门禁或事件，查看上下文、证据和下一步操作。",
    taskLane: "暂无任务",
    artifacts:
      "当前任务流还没有产物。当 Agent 创建 artifact.created 事件后，截图、报告、日志和审核结果会出现在这里。",
  },
  routing: {
    selectedTask: "选中任务",
    includeTaskContext: "携带任务上下文",
    agentOnly: "仅 Agent",
    taskContext: "任务上下文",
    targetAgent: "目标 Agent",
    interruptMessage: "中断内容",
    send: "发送",
  },
} as const;

const stateLabels: Record<string, string> = {
  WAITING_ON_BUS: "等待总线",
  WAIT_RETURNED_NOOP: "空轮询",
  DELIVERED_NOT_ACKED: "已投递待确认",
  WORKING: "工作中",
  SUSPECTED_STUCK: "疑似卡住",
  INPUT_UNAVAILABLE: "输入不可用",
  CONTEXT_LOST: "上下文丢失",
  NEEDS_REHYDRATION: "需要恢复上下文",
  REHYDRATING: "恢复上下文中",
  STANDBY_READY: "待命就绪",
  STANDBY_DEGRADED: "降级待命",
  REPLACED: "已接管",
  CREATED: "已创建",
  ASSIGNED: "已分配",
  ACKNOWLEDGED: "已确认",
  BLOCKED: "阻塞",
  COMPLETED: "已完成",
  FAILED: "失败",
  SUPERSEDED: "已替换",
  REASSIGNED: "已重分配",
  QUEUED: "排队中",
  READY: "待审核",
  PENDING: "等待门禁",
  OPEN: "开放",
  APPROVED: "已批准",
  REJECTED: "已拒绝",
  UNKNOWN: "待更新",
};

const toneLabels: Record<Tone, string> = {
  good: "正常",
  warn: "注意",
  bad: "异常",
  info: "信息",
};

export function stateLabel(state: string): string {
  return stateLabels[state] ?? stateLabels[state.toUpperCase()] ?? state;
}

export function toneLabel(tone: Tone): string {
  return toneLabels[tone];
}
