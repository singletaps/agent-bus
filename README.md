# Agent Bus

Agent Bus 是一个用于实验“多 Codex Agent 长时协作”的本地运行控制台。它把多个子 Agent 看成常驻 worker，通过 SQLite 事件日志、Agent inbox、上下文包、任务流、门禁、替换接管和 React 运维前端来协调工作。

这个项目的核心问题不是“怎样让几个进程互相发消息”，而是：当多个 Agent 同时执行、失联、上下文失效、需要 QA 或需要接管时，系统能否保留可审计的事实链路，并让前端准确呈现当前 workflow。

## 实验目标

- 让多个 Agent 作为长期存在的执行者，而不是一次性脚本。
- 用同一条事件日志记录注册、任务、通信、门禁、审查、上下文失效和接管。
- 让每个 Agent 只从自己的 inbox 和 context packet 获取可执行上下文。
- 当 Agent 卡住、失去输入、上下文损坏或心跳过期时，能够被发现、降级、替换或重新水合。
- 通过前端 Operations Console 观察完整 workflow，包括行动队列、地铁图、通信空间、任务流、门禁和产物。

## 系统结构

```text
Operator / User
    |
    | 发送指令、创建任务、批准门禁、批准接管
    v
FastAPI server
    |
    | 读写 SQLite event log
    v
Agent Bus runtime
    |
    |-- EventStore: 所有事实的追加式日志
    |-- InboxStore: 每个 Agent 的待处理队列
    |-- ContextStore: Agent 可执行上下文包
    |-- TaskBoard: run/task 状态机
    |-- GateBoard: QA/发布/高风险门禁
    |-- ReplacementCoordinator: Agent 替换与 rehydration
    v
React Operations Console
```

SQLite 是事实源。前端、API projection、地铁图和 action queue 都是从 durable runtime state 推导出来的视图。

## 实验方法

推荐的实验方式是用一个 live SQLite 数据库启动服务，再开多个终端分别模拟不同 Agent。

1. 初始化并启动服务：

```powershell
Set-Location 'C:\Users\laptopofzy\Documents\Agent bus'
$Db = 'coordination\live-agent-bus.sqlite3'

python -m agent_bus init --db $Db --json
python -m agent_bus serve --host 127.0.0.1 --port 8787 --db $Db
```

2. 注册 4 个 Agent：

```powershell
python -m agent_bus agent register sim-controller --role controller --capability orchestration --db $Db --json
python -m agent_bus agent register sim-frontend --role worker --capability react --db $Db --json
python -m agent_bus agent register sim-backend --role worker --capability python --capability react --db $Db --json
python -m agent_bus agent register sim-qa --role qa --capability verification --db $Db --json
```

3. 每个 Agent 独立等待 inbox：

```powershell
python -m agent_bus wait --agent sim-frontend --timeout 300 --db $Db --json
python -m agent_bus wait --agent sim-backend --timeout 300 --db $Db --json
python -m agent_bus wait --agent sim-qa --timeout 300 --db $Db --json
python -m agent_bus wait --agent sim-controller --timeout 300 --db $Db --json
```

4. 模拟用户创建任务：

```powershell
python -m agent_bus task create 'Repair workflow metro UI' `
  --run-title 'Metro workflow experiment' `
  --objective 'Verify task assignment, communication, QA gate, and replacement handoff.' `
  --owner sim-controller `
  --assignee sim-frontend `
  --priority 10 `
  --db $Db `
  --json
```

5. Agent 读取任务后按状态推进：

```powershell
python -m agent_bus task ack <task_id> --actor sim-frontend --db $Db --json
python -m agent_bus task progress <task_id> --actor sim-frontend --db $Db --json
```

6. 打开前端观察：

```text
http://127.0.0.1:8787/
```

在前端中重点检查：

- Home 行动队列中的每个卡片是否都有自己的 workflow 小地铁图。
- 通信页按 `全部`、`仅我发送`、`@ 我的`、`关注的 Agent` 筛选时是否真实改变消息列表。
- Runs 页面是否显示真实 task owner、assignee、state。
- Gates 页面是否显示 QA gate、risk、owner 和决策状态。
- Diagnostics 是否能看到 stale、suspected stuck、replacement 等异常状态。

## Agent 类型

项目没有把 Agent 写死成固定四类，但实验中通常使用这些角色：

| Agent | 典型职责 |
| --- | --- |
| controller | 分配任务、批准替换、处理高风险门禁、协调优先级 |
| worker | 执行具体开发、文档、调试、验证任务 |
| qa | 发起或处理 QA gate，提交 verification result |
| helper | 辅助 worker 做检查、补丁、报告或重试 |
| observer | 观察运行状态，通常不直接改动任务 |

每个 Agent 有稳定 identity，也可以有多个 session。identity 表示“这个 Agent 是谁”，session 表示“这次运行窗口/进程是否还活着”。

## Agent 运行状态

`AgentRuntimeState` 是实验的关键观测面：

| 状态 | 含义 |
| --- | --- |
| `STANDBY_READY` | Agent 空闲且可接新任务 |
| `WAITING_ON_BUS` | Agent 正在阻塞等待 inbox |
| `WAIT_RETURNED_NOOP` | wait 超时，没有取到任务 |
| `DELIVERED_NOT_ACKED` | inbox 已投递但 Agent 尚未 ack |
| `WORKING` | Agent 正在执行任务 |
| `STANDBY_DEGRADED` | 表面空闲，但心跳过期或健康降级 |
| `SUSPECTED_STUCK` | working 状态心跳过期，疑似卡住 |
| `INPUT_UNAVAILABLE` | Agent 输入不可用，无法继续交互 |
| `CONTEXT_LOST` | Agent 报告上下文丢失或损坏 |
| `NEEDS_REHYDRATION` | 需要重新注入上下文 |
| `REHYDRATING` | replacement Agent 正在接收 rehydration packet |
| `REPLACED` | 旧 session 已被新 session 接管 |

状态不是只靠 Agent 自报。Projection 会根据 `last_seen_at` 判断心跳新鲜度：ready/waiting/noop 过期会显示为 degraded；working 过期会显示为 suspected stuck。

## Agent 如何沟通

Agent Bus 的通信分三层。

第一层是事件日志。所有 durable 行为都会 append 一个 event，例如：

```text
agent.registered
agent.session_started
task.created
task.assigned
task.progress
gate.opened
gate.result
user.interrupt_created
replacement.recommended
replacement.approved
```

第二层是 inbox。任务分派、用户打断、context invalidation、gate result、replacement notice 都会进入目标 Agent 的 inbox。Agent 通过 `wait` 拉取消息，处理后用 `ack` 确认。

第三层是 communication message projection。前端通信页用 `/api/messages/send` 写入消息事件，再通过 `/api/projections/messages` 展示消息流。消息包含：

```text
sender_agent_id
recipient_agent_ids
message_type
delivery_state
ack_state
reply_state
priority
links.run_id
links.task_ids
links.gate_ids
links.artifact_ids
```

这让一条消息可以挂在 run、task、gate 或 artifact 上，避免通信和 workflow 脱节。

## Context Packet

Context packet 是 Agent 真正执行任务时应读取的权威上下文。它可以包含：

- 当前 role contract
- 当前 task 和 run
- 上次已知摘要
- 指令和下一步动作
- 需要参考的 artifact
- 当前 open inbox item
- 被 invalidated 的旧 packet

普通 Agent 流程：

```powershell
python -m agent_bus wait --agent sim-frontend --timeout 300 --db $Db --json
python -m agent_bus context get <context_packet_id> --db $Db --json
python -m agent_bus ack <inbox_id> --agent sim-frontend --db $Db --json
```

如果 context packet 被 invalidated，Agent 必须停止使用旧上下文，等待 replan 或 rehydration。

## Workflow 与地铁图

前端 Home 的地铁图本质上是 active run 的 workflow projection。后端会从 run、task、gate、artifact 和 agent health 中生成 `ui.metro`。

当前设计里有两层 workflow：

- 全局地铁图：展示 active run 的主路径和当前节点。
- 行动卡小地铁图：每个 action queue item 独享一个 compact workflow strip，用于解释这个行动项属于哪条 run/task/gate 链路。

这避免了“行动队列只是横向卡片滚动”的问题：每个卡片都能看到自己的 workflow 上下文。

## Replacement / 接管实验

Replacement 用于模拟 Agent 卡住或上下文失效后的接管。

典型流程：

1. worker 正在 `WORKING`。
2. worker 变成 `CONTEXT_LOST`、`INPUT_UNAVAILABLE`、`SUSPECTED_STUCK` 或长时间未心跳。
3. `ReplacementCoordinator` 根据 capability、role、freshness、ready state 给候选 Agent 打分。
4. controller 批准接管。
5. 旧 session 标记为 `REPLACED`。
6. replacement session 标记为 `REHYDRATING`。
7. 同一个 task 被 `reassigned` 到 replacement agent。
8. replacement agent 收到 `replacement_notice` 和 rehydration packet，继续同一个 task。

示例：

```powershell
python -m agent_bus replacement approve `
  --old-session-id <old_session_id> `
  --task-id <task_id> `
  --run-id <run_id> `
  --candidate-agent sim-backend `
  --required-capability react `
  --role worker `
  --approved-by sim-controller `
  --db $Db `
  --json
```

非终态任务会同步变成 `reassigned`。已经 `completed`、`failed` 或 `superseded` 的任务不会被重新改写状态，但仍可保留 replacement approval 的历史上下文。

## 前端页面

| 页面 | 用途 |
| --- | --- |
| 控制首页 | active run、行动队列、workflow 地铁图、Agent 摘要 |
| 通信 | 消息空间、消息范围筛选、发送指令、查看消息详情 |
| 任务流 | run/task 状态、assignee、progress、gate/artifact 关联 |
| 门禁 | QA gate、risk、owner、approve/reject/escalate |
| 产物 | artifact manifest、preview/download 链接 |
| 诊断 | Agent health、session freshness、异常状态 |
| 设置 | 控制台配置入口 |

## 开发和验证

安装前端依赖：

```powershell
Set-Location 'C:\Users\laptopofzy\Documents\Agent bus\frontend'
npm install
```

运行测试：

```powershell
Set-Location 'C:\Users\laptopofzy\Documents\Agent bus'
pytest -q

Set-Location 'C:\Users\laptopofzy\Documents\Agent bus\frontend'
npx tsc --noEmit
npx vite build
```

最近一次完整验证：

```text
pytest -q            -> 67 passed
npx tsc --noEmit     -> passed
npx vite build       -> passed
```

## 重要目录

```text
agent_bus/      Python runtime、CLI、FastAPI server、projection
frontend/       React Operations Console
tests/          后端和 API 测试
docs/           协议、操作手册、恢复手册
skills/         Agent Bus skill 文档
coordination/   本地实验记录、截图、live sqlite/log 文件
5-29/           UI 目标示意图和参考材料
```

`coordination/` 中的 sqlite、wal、log、截图通常是本地实验产物，不建议作为源代码提交；需要保留证据时，优先提交 markdown/json 摘要。
