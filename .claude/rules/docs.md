---
paths:
  - "docs/**/*.md"
  - "AGENTS.md"
  - "README.md"
---

# Docs: rules an agent must not miss

Source of truth: docs/handbook/quy-uoc-code.md (Kiểm tra và commit) and docs/reports/README.md.

- Write Vietnamese with diacritics, UTF-8; relative links only (broken links fail `scripts/check_conventions.py`).
- API docs state the date or status (**đã triển khai** / **dự kiến**) and keep current behavior apart from design decisions.
- Each module has `docs/handbook/modules/<module>/` with one file per API flow; update the module table in docs/handbook/README.md.
- Reports go in docs/reports as `YYYY-MM-DD-chu-de.md` with date, commit, steps checked and limits; never a secret or a URI with a password.
