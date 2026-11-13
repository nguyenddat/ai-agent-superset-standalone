# AI Agent Superset Standalone

## Database migrations

This project uses Alembic for its own metadata database. Set `DATABASE_URL` to
the application's PostgreSQL database URL before running migration commands.
The URL must use the `postgresql+psycopg://` driver. `.env.example` shows the
expected format; a local `.env` file is ignored by Git, but is not loaded
automatically.

In PowerShell:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://app:password@localhost:5432/ai_agent"
uv run alembic upgrade head
```

To add a table, define a SQLAlchemy model inheriting from
`ai_agent_superset_standalone.database.base.Base`, import it in
`database/models/__init__.py`, then generate and review a migration:

```powershell
uv run alembic revision --autogenerate -m "add connection table"
uv run alembic upgrade head
```

The first revision is an empty baseline. This setup does not migrate the
Superset metadata database.
