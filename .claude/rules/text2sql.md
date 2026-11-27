---
paths:
  - "backend/modules/text2sql/**"
  - "backend/agent_package/**"
---

# Text2SQL agent: rules an agent must not miss

Source of truth: docs/handbook/modules/text2sql/api-chat.md (PII, results) and docs/handbook/modules/agent_package.md.

- Source databases are queried read-only through `sql_guard`; never widen what it allows without a test that proves the old rejections still hold.
- Rows are masked by `PiiMasker` right after SQL runs, before steps, chart suggestion and any LLM input; graph state and checkpoints keep labels, everything sent to the user is unmasked.
- `agent_package` never imports from `backend/modules` (checked); prompts live in `agent_package/prompts/`.
- Tests use fake LLMs and in-memory SQLite; the live eval (`scripts/text2sql_eval`) costs money and needs approval.
