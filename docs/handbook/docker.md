# Chạy stack bằng Docker Compose

**Trạng thái:** đã có image backend, image frontend, PostgreSQL, Qdrant và `ingestion-worker` trong `compose.yaml`.

## Chuẩn bị

Từ gốc repository, sao chép `.env.example` thành `.env`. Đổi `POSTGRES_PASSWORD` và tạo `CONNECTION_ENCRYPTION_KEY` bằng lệnh ghi trong file mẫu. Không commit `.env`; khóa Fernet phải được giữ ổn định để đọc lại URI nguồn đã mã hóa. `POSTGRES_USER` và `POSTGRES_DB` có giá trị mặc định trong Compose. Đặt `OPENROUTER_API_KEY` nếu dùng tự động điền từ điển hoặc Text2SQL ingestion/retrieve; để trống thì API tương ứng trả 503.

Đồng bộ metric từ Superset cần `SUPERSET_URL`, `SUPERSET_USERNAME` và `SUPERSET_PASSWORD`. URL phải truy cập được từ container backend; nếu Superset chạy trên Docker Desktop với cổng host `8089`, dùng `http://host.docker.internal:8089` thay cho `localhost`.

```powershell
Copy-Item .env.example .env
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
docker compose up --build -d
docker compose ps
```

Dán khóa vừa tạo vào `.env`. `DATABASE_URL` trong `.env` dùng cho lệnh backend chạy trực tiếp trên máy và trỏ `localhost`; container backend tự dùng hostname `postgres` trong mạng Compose. Nếu đổi mật khẩu trong `.env`, cập nhật `DATABASE_URL` cho lệnh chạy trực tiếp tương ứng. Mật khẩu dùng trong URL cần được URL-encode khi có ký tự đặc biệt.

## Các service

| Service | Image hoặc build | Truy cập từ máy |
| --- | --- | --- |
| `postgres` | `postgres:17-alpine` | `localhost:5432` |
| `qdrant` | `qdrant/qdrant:v1.20.1` | `http://localhost:6333` (REST), `http://localhost:6333/dashboard` |
| `ingestion-worker` | `backend/Dockerfile`, lệnh `python -m backend.modules.text2sql.worker` | không mở cổng |
| `backend` | `backend/Dockerfile`, Python 3.14 và uv | `http://localhost:8000` |
| `frontend` | `frontend/Dockerfile`, Next.js standalone | `http://localhost:3000` |

PostgreSQL lưu dữ liệu trong named volume `postgres_data`. Compose đợi database đạt healthcheck rồi backend chạy `alembic upgrade head`; frontend khởi động sau khi backend khỏe. API cho phép CORS từ `http://localhost:3000`.

Qdrant lưu index trong named volume `qdrant_data`; cổng REST mặc định `6333`, đổi được bằng `QDRANT_PORT`. Container cùng mạng Compose truy cập `http://qdrant:6333`. Backend tạo collection và nạp dữ liệu khi đồng bộ Text2SQL lần đầu. Có thể kiểm tra service bằng `http://localhost:6333/healthz` sau khi khởi động.

`ingestion-worker` dùng chung image với `backend` và khởi động sau khi backend khỏe (migration đã xong). Nó lấy job từ bảng `technical.text2sql_ingestion_jobs`, chạy song song theo topic, tự phát lịch và nhận job do backend xếp khi dữ liệu đổi. Airflow không còn dùng cho ingestion; service `airflow` trong profile `simulation` chỉ nạp dữ liệu thời tiết. Biến cấu hình `TEXT2SQL_WORKER_*`, `TEXT2SQL_JOB_*` và `TEXT2SQL_TOPIC_INTERVALS` ở [worker và hàng đợi](modules/text2sql/worker-ingestion.md); các API ở [API job](modules/text2sql/api-ingestion-jobs.md). Biến `TEXT2SQL_QUERY_*`, `TEXT2SQL_AGENT_*` và `TEXT2SQL_TIMEZONE` của route chat ở [hỏi đáp](modules/text2sql/api-chat.md).

Nếu cổng host bị chiếm, đặt `POSTGRES_PORT`, `BACKEND_PORT` hoặc `FRONTEND_PORT` trong `.env`. Trình duyệt không gọi backend trực tiếp nên đổi cổng backend không cần build lại frontend. Compose tự đặt `FRONTEND_ORIGIN` cho CORS theo `FRONTEND_PORT`, gồm cả `localhost` và `127.0.0.1` vì trình duyệt coi đây là hai origin khác nhau. `FRONTEND_ORIGIN` nhận nhiều origin, phân tách bằng dấu phẩy.

Frontend gọi backend qua mạng Docker tại `API_URL=http://backend:8000` và gắn `TEXT2SQL_SERVICE_KEY` từ `.env`; khóa này bắt buộc, thiếu thì cả backend lẫn proxy trả 503. Khi đăng ký database nguồn từ backend container, URI trỏ service PostgreSQL trong Compose phải dùng hostname `postgres`, không dùng `localhost`.

## Lệnh vận hành

```powershell
docker compose logs -f backend
docker compose exec backend alembic current
docker compose down
```

`docker compose down` giữ volume PostgreSQL. Chỉ xóa volume khi chủ động muốn xóa toàn bộ dữ liệu cục bộ. API đòi `X-Service-Key` (xem [hành vi API](hanh-vi-api.md)), chưa phân quyền theo người dùng; các cổng trong Compose chỉ bind vào `127.0.0.1` để phục vụ phát triển trên máy cá nhân.

## Simulation weather warehouse

**Trạng thái:** đã triển khai, sao chép từ `ai-agent-superset-extension/simulation/` (bỏ phần bootstrap Superset).

`simulation/` gồm hai thành phần, chạy dưới profile `simulation` nên không khởi động cùng stack chính:

| Service | Vai trò | Truy cập từ máy |
| --- | --- | --- |
| `warehouse-db` | PostgreSQL `data_wh`, tạo bảng `dm_*`, `tb_*`, `dim_*`, `fact_*` bằng `simulation/data_wh/scripts/` ở lần khởi tạo volume đầu tiên | `localhost:15433` |
| `airflow` | DAG `weather_warehouse_ingest` chạy mỗi giờ, lấy dữ liệu 12 thành phố từ Open-Meteo rồi gọi `lam_moi_du_lieu_dashboard()` | `http://localhost:18080`, tài khoản `admin`/`admin` |

```powershell
docker compose --profile simulation up --build -d warehouse-db airflow
docker compose --profile simulation logs -f airflow
```

Để thử với ứng dụng, thêm kết nối có URI `postgresql+psycopg://bi:bi_dev_password@warehouse-db:5432/data_wh` rồi đồng bộ metadata. Hostname `warehouse-db` chỉ dùng được từ backend container; công cụ trên máy dùng `localhost:15433`. Cổng, tài khoản và tên database đổi được bằng `WAREHOUSE_DB_PORT`, `AIRFLOW_PORT`, `WAREHOUSE_DB_USER`, `WAREHOUSE_DB_PASSWORD`, `WAREHOUSE_DB`. DAG cần Internet để gọi Open-Meteo.

Script SQL chỉ chạy khi volume `warehouse_db_data` còn trống. Khi sửa script, chạy `docker compose --profile simulation down -v` để khởi tạo lại; lệnh này cũng xóa volume `postgres_data` của ứng dụng. Muốn giữ dữ liệu ứng dụng, xóa riêng volume warehouse bằng `docker volume rm`.
