# Marvis Agent Workstation Research

Created by: `runtime-helper-1`

## Sources Checked

- [The Paper: Tencent launches OS-level AI assistant Marvis](https://www.thepaper.cn/newsDetail_forward_33204640)
- [China Science Daily: Tencent launches OS-level AI assistant Marvis](https://www.stdaily.com/web/gdxw/2026-05/21/content_520218.html)
- [AIGC tool directory: Marvis overview](https://www.aigc.cn/marvis)
- [AIG123: Marvis listing](https://www.aig123.com/sites/8688.html)
- [Sina Finance / Kuai Technology report](https://finance.sina.com.cn/stock/t/2026-05-21/doc-inhyrmms9159146.shtml)

## Stable Facts From Public Reports

- Marvis / 马维斯 is publicly described as a Tencent OS-level personal AI assistant that launched around May 20-21, 2026.
- Reports describe a built-in multi-agent team: one coordinating/main Agent plus specialist Agents such as File, Computer, App, Browser, and Search.
- Reports emphasize system/file/app/web operation through natural language rather than chat-only Q&A.
- Some secondary reports describe visible virtual "小牛马" Agent roles and idle/working states.

## Design Takeaway For Agent Bus

Borrow the observability pattern, not the consumer companion tone.

Marvis-style presentation helps because it turns abstract agents into visible working entities. Agent Bus has the same problem: `runtime-worker-1 WORKING` or `runtime-qa STANDBY_DEGRADED` is technically accurate but not immediately legible to a tired operator.

For Agent Bus, the right translation is `Agent Workstation`, not mascot:

- Agent identity = a permanent workstation/role.
- Session identity = the current shift at that workstation.
- Task = the current work order.
- State = posture/action/light signal.
- Health/context/inbox/gate = trust and urgency signal.

## What To Adopt

- Compact role-specific station marks for controller, worker, helper, QA, and observer roles.
- State as posture: working, standby, waiting gate, waiting review, stuck, context lost, degraded.
- User-visible action path near state: approve, review, probe, rehydrate, replace, interrupt, or wait.
- Status derived only from runtime data: runtime state, health score, context validity, inbox urgency, task state, and gates.

## What Not To Adopt

- Cute companion/pet tone.
- Large avatars that consume first-screen space.
- Decorative idle states that do not map to protocol reality.
- Fake work, invented telemetry, or sample personas.
- Animation that hides dense operational scanning.

## Recommended Direction

Use small Agent Workstation cards with:

- role marker
- semantic state light
- current task/gate/inbox summary
- session trust signal
- compact next action

The avatar/workstation element should be 10-20% of a card, not the card's main content.
