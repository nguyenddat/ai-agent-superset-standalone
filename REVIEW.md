# Review instructions

Read by the sdlc reviewer and by the PR review in CI before every review. Keep it under a page.

## What blocks a merge (Must fix)
- Behavior breaks, data leaks or is lost, or a rule card (`.claude/rules/`) is broken.
- A source database written to, or the read-only guard (`backend/modules/text2sql/services/sql_guard.py`) widened.
- Unmasked PII reaching an LLM input, graph state or checkpoint; masked labels reaching the user.
- A secret, decrypted URI or password in a response, error message, log, test or doc.
- A released Alembic revision edited, or a model without its revision.

## Should fix
- Risky logic without a test that fails when it breaks.
- A behavior change without the matching update under `docs/handbook/`.

## Do not report
- Anything the linter, formatter or type checker enforces: ruff `E501`/`I` (pyproject.toml), eslint and `tsc`
  (frontend), and `scripts/check_conventions.py` (docstrings, `os.getenv` outside settings, `agent_package`
  imports, broken doc links, missing module handbook folder).
- Generated and vendored paths: `uv.lock`, `frontend/package-lock.json`, the `next dev` block in
  `frontend/AGENTS.md`, released revisions under `backend/migrations/versions/`.

## Cap
- At most five Minor findings; summarize the rest as a count.
