# Reference Visual Layout Gate 2 QA

Runtime QA: `runtime-qa`
Timestamp: `2026-05-29T14:31:59+08:00`
Target: `http://127.0.0.1:8787/`

## Result

`GATE_VISUAL_LAYOUT_WAVE2_PASS`

Wave 2 page work passed independent QA after all required READY tokens arrived:

- `VISUAL_LAYOUT_WAVE2_HOME_READY runtime-helper-1`
- `VISUAL_LAYOUT_WAVE2_COMM_GATES_READY runtime-helper-2`
- `VISUAL_LAYOUT_WAVE2_RUNS_ARTIFACTS_READY runtime-worker-4`

## Command Evidence

- `npm --prefix frontend run build`: passed; Vite built 1769 modules, lucide `use client` warnings only.
- `pytest -q`: passed, `66 passed in 5.41s`.
- Source scan across Wave 2 pages, App shell, shared components, and CSS for placeholder / mojibake markers: clean.
- Real API checks on canonical origin:
  - `/api/projections/operations`: 200
  - `/api/projections/messages`: 200
  - `/api/artifacts/manifests`: 200

## Browser Evidence

Browser report:

- `coordination/gate2-wave2-browser-qa.json`
- `coordination/gate2-wave2-browser-clean-log-qa.json`

Screenshots captured from the canonical backend-backed frontend:

- `coordination/gate2-wave2-home-qa.png`
- `coordination/gate2-wave2-communication-qa.png`
- `coordination/gate2-wave2-runs-qa.png`
- `coordination/gate2-wave2-gates-qa.png`
- `coordination/gate2-wave2-artifacts-qa.png`
- `coordination/gate2-wave2-diagnostics-qa.png`
- `coordination/gate2-wave2-settings-qa.png`

Seven-route metrics:

- Nav count: 7.
- Active nav labels matched: 控制首页, 通信, 任务流, 门禁, 产物, 诊断, 设置.
- No visible mojibake / placeholder question marks detected.
- No visible 404 or API error text detected.
- No document body horizontal overflow.
- No visible button text overflow.
- Sidebar background remained white; page background remained light reference gray; active nav used the blue reference pill.
- Max sampled card radius was 8px.
- Fresh-tab current browser error count: 0.

Safe interaction checks:

- Home action queue button opened one `ActionDrawer` and close worked.
- Communication refresh and list selection worked; detail rail remained present.
- Runs run selector worked.
- Gates tab/card selection worked.
- Artifacts tabs and refresh worked.
- Diagnostics segment buttons worked.
- Settings cards rendered.

## Notes

- The first browser run saw two stale console errors from older built assets in the retained browser log buffer. A fresh-tab rerun produced `currentErrorCount: 0`; the stale entries were not counted as current Gate 2 failures.
- Artifact manifests currently return zero manifest-backed artifacts, so the Artifacts page correctly shows the polished empty-list/detail state.
- Home task names and run data include English where the real backend source data is English; this is accepted as real data, not fake placeholder copy.
