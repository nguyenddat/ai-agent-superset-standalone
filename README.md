# AI Agent Superset Standalone

Quy ước dự án nằm trong [AGENTS.md](AGENTS.md) và [docs/handbook](docs/handbook/README.md). Báo cáo theo từng đợt được lưu trong [docs/reports](docs/reports/README.md).

## Kiến trúc

Dịch vụ text2sql của WattPrint: trả lời câu hỏi bằng ngôn ngữ tự nhiên trên một cơ sở dữ liệu nguồn bằng agent gọi công cụ, kèm quản lý metric, từ điển dữ liệu, thuật ngữ và quy tắc chuyên gia. Trợ lý Wappi của [wattprint-backend](https://github.com/daFoggo/wattprint-backend) gọi dịch vụ này cho câu hỏi dữ liệu tự do.

![Các dịch vụ](docs/diagrams/text2sql-architecture.svg)

| Dịch vụ (`compose.yaml`) | Công nghệ | Cổng | Vai trò |
|---|---|---|---|
| `frontend` | Next.js (shadcn/ui) | 3000 | Quản lý kết nối, từ điển, metric, thuật ngữ, quy tắc, dòng dữ liệu, tab "Hỏi dữ liệu" |
| `backend` | FastAPI, LangGraph | 8000 (và `BACKEND_DOCKER_PORT` cho project Compose khác: mặc định 8001, WattPrint dùng 11101) | API `/api/v1`; chạy `alembic upgrade head` khi khởi động |
| `postgres` | PostgreSQL 17 | 5432 | Metadata của chính dịch vụ (schema `technical`) |
| `qdrant` | Qdrant 1.20 | 6333 | Chỉ mục ngữ nghĩa, bộ sưu tập `text2sql_semantics_v1` |
| `ingestion-worker` | `backend.modules.text2sql.worker` | không | Lấy job từ bảng `technical.text2sql_ingestion_jobs` (`FOR UPDATE SKIP LOCKED`), embedding qua OpenRouter, ghi Qdrant |
| `warehouse-db`, `airflow` | Profile `simulation` | 15433, 18080 | Kho dữ liệu giả lập, chỉ chạy khi bật profile |

### Một câu hỏi đi qua đâu

![Đồ thị LangGraph](docs/diagrams/text2sql-chat.svg)

`POST /api/v1/text2sql/chat` (JSON) và `/chat/stream` (SSE) chạy cùng một đồ thị LangGraph (`backend/modules/text2sql/services/chat_graph.py`): `preprocess` viết lại câu hỏi, tách câu phụ, phân loại ý định và truy hồi top 5 từ Qdrant (metric, bảng, cột, thuật ngữ, quy tắc, tri thức riêng); `dispatch` gửi từng câu đơn đã đủ câu phụ thuộc cho `answer_question`; agent trả lời bằng tám công cụ (`get_metric`, `get_table`, `get_expert_rule`, `get_column_values`, `query_metric`, `run_sql`, `make_chart`, `ask_user`); câu cần hỏi lại dừng ở `clarify` bằng `interrupt()` và checkpoint lưu ở `technical.text2sql_chat_checkpoints`; hết câu thì `synthesize` ghép câu trả lời. `run_sql` chỉ chạy một câu `SELECT` đã qua `validate_select`. Chi tiết và danh sách sự kiện SSE: [docs/handbook/modules/text2sql/api-chat.md](docs/handbook/modules/text2sql/api-chat.md).

Mã nguồn backend: [backend/README.md](backend/README.md). Frontend: [frontend/README.md](frontend/README.md).

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

API ở `http://127.0.0.1:8000/api/v1`; OpenAPI ở `/docs`. CORS cho phép các origin trong `FRONTEND_ORIGIN` (mặc định `http://localhost:3000` và `http://127.0.0.1:3000`). Mọi route `/api/v1/*` trừ `own-knowledge` đòi header `X-Service-Key` (xem mục Tích hợp với WattPrint); API không kiểm danh tính người dùng cuối.

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

## Tích hợp với WattPrint

- **Gọi dịch vụ**: backend WattPrint gọi `/api/v1/text2sql/chat/stream` với header `X-Service-Key`. Mọi route `/api/v1/*` (trừ `/api/v1/own-knowledge`, vốn có khóa agent/admin riêng) đòi header này khớp `TEXT2SQL_SERVICE_KEY`: thiếu hoặc sai trả 401; chưa đặt khóa trả 503 (đóng mặc định, không bao giờ mở). Frontend gọi qua proxy cùng nguồn `/api/v1/*` của Next.js, khóa chỉ nằm phía server.
- **Phạm vi một nhà**: body chat có `scope_token` (UUID). Trước mỗi truy vấn, dịch vụ chạy `SELECT set_config('app.copilot_token', :t, true)`; các view `copilot_ro` của WattPrint đọc cài đặt này để chỉ hiện dữ liệu một nhà. Token sống 5 phút và do backend WattPrint tạo.
- **Mạng**: để container của project Compose khác gọi tới, đặt `BACKEND_DOCKER_BIND` (ví dụ `172.17.0.1`) và `BACKEND_DOCKER_PORT` (ví dụ `11101`) trong `.env`; WattPrint truy cập qua `host.docker.internal:11101`.
- **Kết nối nguồn**: đăng ký cơ sở dữ liệu nguồn qua API `database_connection`; từ container backend, URI phải dùng tên máy trong mạng Compose. Tài liệu repo chưa có quy trình riêng cho WattPrint (role `wattprint_copilot_ro`, id kết nối); id này là `TEXT2SQL_CONNECTION_ID` phía WattPrint.

## Biến môi trường chính (`.env.example`)

| Nhóm | Biến |
|---|---|
| Cơ sở dữ liệu | `DATABASE_URL`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |
| Bảo mật | `CONNECTION_ENCRYPTION_KEY` (khóa Fernet, bắt buộc), `TEXT2SQL_SERVICE_KEY`, `OWN_KNOWLEDGE_AGENT_KEY`, `OWN_KNOWLEDGE_ADMIN_KEY` |
| LLM và embedding | `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `OPENROUTER_MODEL`, `TEXT2SQL_EMBEDDING_MODEL` (mặc định `openai/text-embedding-3-small`, 1536 chiều) |
| Qdrant | `QDRANT_URL`, `QDRANT_PORT`, `TEXT2SQL_COLLECTION` |
| Agent | `TEXT2SQL_QUERY_TIMEOUT_SECONDS`, `TEXT2SQL_QUERY_MAX_ROWS`, `TEXT2SQL_AGENT_MAX_STEPS`, `TEXT2SQL_TIMEZONE` |
| Worker | `TEXT2SQL_WORKER_CONCURRENCY`, `TEXT2SQL_WORKER_POLL_SECONDS`, `TEXT2SQL_JOB_*`, `TEXT2SQL_TOPIC_INTERVALS` |
| Mạng | `BACKEND_DOCKER_BIND`, `BACKEND_DOCKER_PORT`, `FRONTEND_PORT`, `BACKEND_PORT`, `POSTGRES_PORT` |

Kiểm tra: `scripts/verify.sh` (khoảng 80 giây, cần `uv` và Node 22+) và `npm run test` trong `frontend/`. Chưa có CI.
