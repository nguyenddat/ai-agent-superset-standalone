---
paths:
  - "frontend/**"
---

# Frontend: rules an agent must not miss

Source of truth: frontend/AGENTS.md and docs/handbook/frontend/README.md.

- Next.js 16.4 differs from training data: read the guide in `frontend/node_modules/next/dist/docs/` before writing code.
- shadcn components come from `npx shadcn@latest add <name>`, Hairline ones from `https://hairlineui.com/r/<name>.json`; keep visible strings Vietnamese.
- Colors use the `--chart-*` tokens in `app/globals.css`; one status keeps one color on every card.
- Chart logic in `features/text2sql/charts` shares `tests/fixtures/*_cases.json` with the backend: change both sides together.
- Update docs/handbook/frontend/README.md with the change.
