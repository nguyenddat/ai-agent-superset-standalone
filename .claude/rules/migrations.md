---
paths:
  - "backend/migrations/**"
  - "backend/modules/*/models/**"
  - "alembic.ini"
---

# Migrations: rules an agent must not miss

Source of truth: docs/handbook/du-lieu-va-migration.md. Open it for the revision chain and the technical schema.

- Never edit a released revision; add a new one with `--version-path backend/migrations/versions/init_<module>_module`.
- A new module folder goes into `version_locations` in `alembic.ini`.
- Queue and job tables live in schema `technical` (`TECHNICAL_SCHEMA`), and the revision runs `CREATE SCHEMA IF NOT EXISTS technical` first.
- Check upgrade, `alembic check` and downgrade on a scratch database only; never on the running stack (localhost:11102) or a source database. No `create_all()` in startup.
