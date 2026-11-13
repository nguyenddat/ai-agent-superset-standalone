# Chạy stack bằng Docker Compose

**Trạng thái:** đã có image backend, image frontend và PostgreSQL trong `compose.yaml`.

## Chuẩn bị

Từ gốc repository, sao chép `.env.example` thành `.env`. Đổi `POSTGRES_PASSWORD` và tạo `CONNECTION_ENCRYPTION_KEY` bằng lệnh ghi trong file mẫu. Không commit `.env`; khóa Fernet phải được giữ ổn định để đọc lại URI nguồn đã mã hóa. `POSTGRES_USER` và `POSTGRES_DB` có giá trị mặc định trong Compose. Đặt `OPENROUTER_API_KEY` nếu dùng tính năng tự động điền từ điển dữ liệu; để trống thì API đó trả 503.

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
| `backend` | `backend/Dockerfile`, Python 3.14 và uv | `http://localhost:8000` |
| `frontend` | `frontend/Dockerfile`, Next.js standalone | `http://localhost:3000` |

PostgreSQL lưu dữ liệu trong named volume `postgres_data`. Compose đợi database đạt healthcheck rồi backend chạy `alembic upgrade head`; frontend khởi động sau khi backend khỏe. API cho phép CORS từ `http://localhost:3000`.

Nếu cổng host bị chiếm, đặt `POSTGRES_PORT`, `BACKEND_PORT` hoặc `FRONTEND_PORT` trong `.env`. Khi đổi cổng backend, đặt `NEXT_PUBLIC_API_URL` theo cổng mới và build lại frontend. Compose tự đặt `FRONTEND_ORIGIN` cho CORS theo `FRONTEND_PORT`, gồm cả `localhost` và `127.0.0.1` vì trình duyệt coi đây là hai origin khác nhau. `FRONTEND_ORIGIN` nhận nhiều origin, phân tách bằng dấu phẩy.

`NEXT_PUBLIC_API_URL` mặc định là `http://localhost:8000`. Biến này được đưa vào bundle frontend lúc build, nên khi đổi URL phải build lại image. Đây là URL trình duyệt sử dụng, không phải hostname `backend` trong mạng Docker. Khi đăng ký database nguồn từ backend container, URI trỏ service PostgreSQL trong Compose phải dùng hostname `postgres`, không dùng `localhost`.

## Lệnh vận hành

```powershell
docker compose logs -f backend
docker compose exec backend alembic current
docker compose down
```

`docker compose down` giữ volume PostgreSQL. Chỉ xóa volume khi chủ động muốn xóa toàn bộ dữ liệu cục bộ. API hiện chưa có xác thực/phân quyền; các cổng trong Compose chỉ bind vào `127.0.0.1` để phục vụ phát triển trên máy cá nhân.

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
