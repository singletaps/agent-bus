# Frontend Skill Discovery

Created by: `runtime-helper-1`

## Installed Global Skills

These skills were installed under `C:\Users\laptopofzy\.codex\skills` for future Codex sessions:

- `frontend-design` from `Ilm-Alan/frontend-design`
- `ui-design` from `hursh-shah/codex-design-skill/ui-design`
- `frontend-design-review` from `microsoft/skills/.github/skills/frontend-design-review`
- `playwright-interactive` from `openai/skills/skills/.curated/playwright-interactive`
- `generate2dsprite` from `0x0funky/agent-sprite-forge/skills/generate2dsprite`

Note: installed global skills may require a Codex restart for automatic discovery. In this running session, use the repo-scoped skills below and read the installed `SKILL.md` files directly when needed.

## Repo-Scoped Skills

The project now contains:

- `.agents/skills/ux-operator-review`
- `.agents/skills/frontend-design`
- `.agents/skills/frontend-design-review`

Validation:

- `quick_validate.py .agents\skills\ux-operator-review` passed.
- `quick_validate.py .agents\skills\frontend-design` passed.
- `quick_validate.py .agents\skills\frontend-design-review` passed.

## Required Use

Before the next product-code UI pass:

1. Use `ux-operator-review` for a no-code browser review.
2. Use `frontend-design` to choose the Agent Workstation visual direction.
3. Use `frontend-design-review` to define acceptance and gate checks.
4. Use Browser/Playwright for screenshot, desktop QA, and mobile QA.

## Pixel/Sprite Skill Position

`generate2dsprite` is available if the team decides to generate compact Agent workstation/avatar sprites. This does not mean the UI should become cute companion UI. Any generated art must remain small, functional, and protocol-derived.
