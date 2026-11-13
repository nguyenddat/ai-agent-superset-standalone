# AI Agent Superset Standalone

Quy ước dự án nằm trong [AGENTS.md](AGENTS.md) và [docs/handbook](docs/handbook/README.md). Báo cáo theo từng đợt được lưu trong [docs/reports](docs/reports/README.md).

## Project layout

- `backend/`: Python backend package and business modules.
- `backend/migrations/`: Alembic revisions for the backend metadata database.
- `frontend/`: standalone web application workspace.

Run `uv` and Alembic commands from the repository root. The root
`pyproject.toml` packages `backend/`, so `uv add <package>` installs
backend dependencies.

## Shared backend conventions

Module errors inherit from the abstract classes in
`backend/common/base_exceptions.py` and set a module-specific `code` and
default `message`. A route can use each error's `status` and message in its
response.

Store timestamps as timezone-aware UTC `datetime` values in
`DateTime(timezone=True)` columns. `backend/common/utils/type_formatters.py`
serializes them as ISO 8601 with six fractional digits and `Z`; dates use
`YYYY-MM-DD`. JSON scalar formatting keeps strings, integers and booleans in
their original types, renders UUIDs and decimals as strings, and rejects
non-finite numbers.

## Database migrations

This project uses Alembic for its own metadata database. Set `DATABASE_URL` to
the application's PostgreSQL database URL before running migration commands.
The URL must use the `postgresql+psycopg://` driver. `.env.example` shows the
expected format; a local `.env` file is ignored by Git and loaded by
`backend.core.setting.Config`. Environment variables take precedence over it.

In PowerShell:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://app:password@localhost:5432/ai_agent"
uv run alembic upgrade head
```

To add a table, define a SQLAlchemy model inheriting from
`backend.common.base_model.Base`, import it in its module's `models/__init__.py`,
then generate and review a migration:

```powershell
uv run alembic revision --autogenerate --version-path backend/migrations/versions/init_database_module -m "add connection field"
uv run alembic upgrade head
```

Revisions are grouped under `backend/migrations/versions/init_<module>_module/`.
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
