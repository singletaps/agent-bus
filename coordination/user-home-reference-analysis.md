# User Home Reference Analysis

Source image: `用户首屏.png`

Created by: `runtime-helper-1`

## User Direction

The current first screen is too dense because it opens directly into the Operations overview. Add a new Home page above `总览`; keep the dense overview in the sidebar for users who need it.

## Reference Pattern

The image shows:

- navy sidebar
- active "控制首页" nav item
- light blue-white background
- compact page title and run subtitle
- top metric cards
- large current workflow card with progress and primary/secondary actions
- three lower quick cards
- right-side Controller suggestion card
- notification icon in the top-right

## Agent Bus Translation

Default route should become `Home` / `控制首页`.

Keep `总览` as the deeper operations page with the dense Agent Dock, task board, Inspector, Event Console, gates, and command composer.

Home page should use real data only:

- current run: `room.brief.activeRunLabel`, `room.brief.activeRunMeta`, and short run id if needed
- running count: active task lane count
- completed count: done task lane count
- pending approvals: open gate count
- attention count: needs-action lane count or pending inbox
- current workflow: first active task, first needs-action task, or the active run summary
- quick cards: needs action, gates/approvals, recent artifacts/results
- controller suggestion: based on the current top risk or first abnormal task/gate

## Implementation Implication

BW-3 must change from "dense overview first screen" to "Home page first screen + dense overview as side route".

Required frontend changes:

- add `Home` to `ViewName`
- make default active view `Home`
- add sidebar label `控制首页`
- keep `Operations` label as `总览`
- implement Home page component in `App.tsx`
- add Home-specific CSS classes, either in BW-3 if necessary for layout or in BW-4 visual polish
