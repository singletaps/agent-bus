# Reference Visual Layout Gate 1 QA

Timestamp: `2026-05-29T13:56:30+08:00`

Result: `PASS`

## Ready Tokens

- `VISUAL_LAYOUT_WAVE1_SHELL_READY runtime-helper-1`
- `VISUAL_LAYOUT_WAVE1_FOUNDATION_READY runtime-worker-4`

## Independent Verification

- `npm --prefix frontend run build`: passed. Vite built 1769 modules; lucide `use client` warnings only.
- Source scan: no hits for `???`, replacement character, common mojibake clusters, or old dark-shell remnants in Wave 1 files.
- Correct live origin: `http://127.0.0.1:8787/`
- API check: `http://127.0.0.1:8787/api/projections/operations` returned 200.

## Browser Evidence

- Home: `coordination/gate1-wave1-home-real-backend.png`
- Communication: `coordination/gate1-wave1-communication-real-backend.png`

Observed:

- White sidebar: `rgb(255, 255, 255)`.
- Light body background: `rgb(246, 248, 251)`.
- Active nav pill is blue on pale blue with `8px` radius.
- Primary nav labels are clean and visible.
- Top sync toolbar renders auto-refresh and last-sync state.
- No visible `???`, replacement characters, or common mojibake.
- No horizontal document overflow at the tested desktop viewport.
- No 404/API error text on the real backend origin.

## Carry Forward

- Home page content is not yet reference-matched; this is Wave 2 Task 2A scope, not a Wave 1 blocker.
- Communication page content is not yet reference-matched; this is Wave 2 Task 2B scope, not a Wave 1 blocker.
- The temporary Vite-only screenshots showed API 404 because Vite was not the correct backend origin; those screenshots are not used as Gate 1 pass evidence.

