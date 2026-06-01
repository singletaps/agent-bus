# UX Operator Review Round 1

Created by: `runtime-helper-1`

Mode: no product-code edits.

Screenshot reviewed: `coordination/ux-operator-review-before.png`

## 10-Second Comprehension

- System health: partly understandable; top metrics show 7 Agents, 125 pending inbox, 0 open gates, and 0 context risk, but they do not explain whether action is required.
- Active run: not clear in the first 10 seconds. The run id is available elsewhere but not the user's first mental model.
- User-required action: unclear. A failed Worker2 task appears in `需处理`, but the top bar does not call it out as the first action.
- Active agents: visible, but Agent cards read as records with health bars and session IDs rather than working entities.
- Blocked tasks: visible only by reading task cards carefully; completed tasks also appear in a queue lane, which muddies priority.
- First click: likely the Worker2 failed task, but the UI does not explicitly guide this.

## Persona Findings

First-time user: the page says "运行态势", but does not tell the user what Agent Bus is doing right now or what one action matters most.

Daily operator: working/waiting/degraded states are present, but the eye must read every card. There is no strong scan pattern for "healthy, needs attention, quiet".

Incident responder: degraded agents and a failed task exist, but incident diagnosis is not centralized. The next action is not adjacent to the fault.

QA reviewer: no review queue or evidence path is visible in the first screen. Artifacts and acceptance criteria are not obvious.

Tired user: `待处理 inbox 125` and failed task compete with low-action metrics. The urgent item is not visually impossible to miss.

## Top UX Failures

1. High: top bar lacks a single operational sentence and primary action. It shows counts but not "what should I handle first".
2. High: Agent Dock still feels like a debug/session list. Workstation identity, posture, trust, and next action are not visually encoded.
3. High: Task lanes mix operational concerns. Failed, queued, completed, and active work are not arranged by operator decision path.
4. Medium: raw IDs, session IDs, and long task text still dominate too much primary surface.
5. Medium: Gate/review/evidence workflow is below the current first-screen hierarchy, so QA and incident personas need to hunt.

## Planned UI Changes

1. Introduce an Operations Brief at the top: system state sentence, strongest required action, active run, and quiet/attention summary.
2. Convert Agent Dock into Agent Workstation cards with role marker, protocol-derived state light, task/gate/inbox summary, session trust, and compact next action.
3. Rework Operations first-screen lanes around operator decisions: `需要处理`, `进行中`, `等待/待命`, and `已完成/归档` only where useful.
4. Move failed task/gate/review evidence into a stronger Inspector/Action Panel pattern so the first click is obvious.
5. Make Event Console a structured digest with severity, source, target, and action relevance instead of a chat-like stream.

## Non-Goals For This Pass

- Do not redesign backend data contracts.
- Do not add fake avatar personalities or decorative companions.
- Do not touch BUG-2 routing logic.
- Do not redesign every route; start with Operations first screen.
- Do not hide raw IDs entirely; demote them to detail surfaces.

## Gate Criteria For Next Pass

- First-time user can explain system health within 10 seconds.
- Daily operator can identify working, waiting, stuck, and degraded agents by scan.
- Incident responder sees one clear first action for failed/stale/context/gate states.
- QA reviewer can find evidence and gate decision path from the selected task.
- Mobile viewport has no horizontal overflow and preserves the same hierarchy.
