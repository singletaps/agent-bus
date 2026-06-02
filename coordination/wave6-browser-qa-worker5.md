# Wave6 Browser QA - runtime-worker-5

Checked at: 2026-06-02 15:54 Asia/Shanghai

## Scope

Owned artifact only: `coordination/wave6-browser-qa-worker5.md`.

No frontend or product code changes were made for Wave6. The live service at `http://127.0.0.1:8787/` was used with `coordination/live-agent-bus.sqlite3`.

## Browser Checks

Playwright inspected these in-page tabs through the running console:

- Desktop 1440x950: Home, Communication, Diagnostics.
- Mobile 390x844: Home, Communication, Diagnostics.

Screenshots were captured in the Playwright session for desktop Home, desktop Communication, desktop Diagnostics, and mobile Diagnostics. They were not saved as separate files so this package only writes the authorized markdown artifact.

## Results

- Home is reachable through tab navigation and renders the task workflow graph.
- Communication is reachable through tab navigation and renders real message cards plus category/search/filter controls.
- Diagnostics is reachable through tab navigation and renders protocol/projection diagnostic panels.
- Desktop document horizontal overflow: false on Home, Communication, Diagnostics.
- Mobile document horizontal overflow: false on Home, Communication, Diagnostics.
- Tab-navigation console errors/warnings: none observed.
- Operations API reachable: yes.

API facts from `/api/projections/operations`:

- `task_workflow` nodes: 87.
- `task_workflow` task id count: 1.
- `task_workflow` node kinds: context, gate, replacement, start, task.
- Legacy `ui.metro` node kinds: gate, start, task.
- Cross-task workflow edges detected: 0.
- Diagnostics counts: projection effects 12, protocol violations 120, fencing rejects 0, deprecated adapter events 0.

## Known Non-Blocking Finding

- Direct URL navigation to `/communication` and `/diagnostics` returns HTTP 404. This matches the Wave5 QA residual risk: the console currently uses in-page tab navigation rather than server-side SPA fallback. In-page navigation to Communication and Diagnostics works.

## Conclusion

No new browser QA findings from runtime-worker-5. The Wave5 frontend convergence invariants still hold on the running 8787 console.
