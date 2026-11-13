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
uv run alembic revision --autogenerate --version-path migrations/versions/init_database_module -m "add connection field"
uv run alembic upgrade head
```

Revisions are grouped under `migrations/versions/init_<module>_module/`.
When adding a module, create its folder and add that path to `version_locations`
in `alembic.ini`; pass its folder with `--version-path` when generating a
revision. The baseline revision remains at the root of `versions/`.

The database module migrations create `database_connections`, then
`database_schemas`, `database_tables`, and `database_columns`. The latter three
are snapshots of metadata discovered in registered source databases; these
migrations do not create tables in those source databases. `uri_ciphertext`
must contain an encrypted connection URI; the encryption and connection API
will be added with the backend service. `DATABASE_URL` always points to the
application metadata database, not to a registered source database. This
setup does not migrate the Superset metadata database.
