# AI Agent Superset Standalone

Quy ước dự án nằm trong [AGENTS.md](AGENTS.md) và [docs/handbook](docs/handbook/README.md). Báo cáo theo từng đợt được lưu trong [docs/reports](docs/reports/README.md).

## Chạy bằng Docker Compose

Sao chép `.env.example` thành `.env`, đổi `POSTGRES_PASSWORD` và tạo `CONNECTION_ENCRYPTION_KEY` theo lệnh ghi trong file. Sau đó chạy:

```powershell
docker compose up --build -d
docker compose ps
```

Stack chính gồm PostgreSQL metadata, Qdrant, backend, `ingestion-worker` và frontend. Qdrant REST API ở `http://localhost:6333` (cổng đổi bằng `QDRANT_PORT`); dữ liệu index nằm trong volume `qdrant_data`. `ingestion-worker` đồng bộ sáu loại dữ liệu sang Qdrant theo lịch riêng từng loại và ngay khi người dùng cập nhật dữ liệu ([worker và hàng đợi](docs/handbook/modules/text2sql/worker-ingestion.md)). Backend có [API xếp job ingest lại](docs/handbook/modules/text2sql/api-ingestion-jobs.md) và [API đồng bộ trực tiếp, truy hồi top K metric](docs/handbook/modules/text2sql/api-ingestion-retrieve.md). Cần `OPENROUTER_API_KEY` để tạo embedding qua OpenRouter.

Web ở `http://localhost:3000`, API ở `http://localhost:8000/api/v1`, OpenAPI ở `http://localhost:8000/docs`. Backend tự chạy `alembic upgrade head` sau khi PostgreSQL khỏe. Dữ liệu PostgreSQL nằm trong volume `postgres_data`. Xem [hướng dẫn Docker](docs/handbook/docker.md) để biết các lệnh vận hành và giới hạn hiện tại.

## Project layout

- `backend/`: Python backend package and business modules.
- `backend/migrations/`: Alembic revisions for the backend metadata database.
- `frontend/`: standalone web application workspace.

Frontend dùng Next.js App Router và được khởi tạo bằng `create-next-app`. Chạy riêng:

```powershell
cd frontend
npm install
npm run dev
```

Trang chính mở tại `http://localhost:3000` và chưa có luồng đăng nhập. Xem [hướng dẫn frontend](frontend/README.md).

Trong trang chi tiết kết nối, tab `Từ điển` cho phép chọn bảng đã đồng bộ metadata, sửa mô tả bảng và cột, rồi lưu thay đổi. Tính năng `Tự động điền` gợi ý mô tả bằng AI khi `OPENROUTER_API_KEY` được cấu hình. Xem [handbook Data Dictionary](docs/handbook/modules/data_dictionary/README.md) để biết API và phần đã triển khai.

Backend API dùng FastAPI. Sau khi cấu hình `DATABASE_URL`, `CONNECTION_ENCRYPTION_KEY` và chạy migration, khởi động từ gốc repository:

```powershell
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

API ở `http://127.0.0.1:8000/api/v1`; OpenAPI ở `/docs`. CORS cho phép các origin trong `FRONTEND_ORIGIN` (mặc định `http://localhost:3000` và `http://127.0.0.1:3000`). Hiện API chưa có xác thực, nên chỉ dùng trong môi trường phát triển tin cậy.

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
