#!/usr/bin/env bash
# Every fast check, from the repository root. Needs uv and Node 22+ (test:charts uses node --test type stripping).
# Tests never touch the running stack: DATABASE_URL, Qdrant and the LLM key from .env are overridden.
set -euo pipefail
cd "$(dirname "$0")/.."

git diff --check
uvx ruff@0.17.6 check
uv run --frozen python scripts/check_conventions.py
DATABASE_URL=postgresql+psycopg://verify:verify@127.0.0.1:9/verify_isolated QDRANT_URL=http://127.0.0.1:9 \
  OPENROUTER_API_KEY= TEXT2SQL_SERVICE_KEY= uv run --frozen python -m unittest discover -s tests 2>&1 | tail -n 4

cd frontend
[ -d node_modules ] || npm ci --no-audit --no-fund
npm run -s lint
npm run -s typecheck
npm run -s test:charts | tail -n 8
