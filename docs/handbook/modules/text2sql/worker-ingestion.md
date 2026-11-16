# Worker và hàng đợi ingestion

**Trạng thái:** đã triển khai. Service `ingestion-worker` trong `compose.yaml`; chạy riêng bằng `uv run python -m backend.modules.text2sql.worker`.

## Vì sao worker nằm trong backend

Airflow là hệ thống riêng (scheduler, webserver, database), không nhúng được vào tiến trình backend, và việc nó làm ở đây chỉ là gọi HTTP theo lịch. Lịch song song theo topic lại cần đổi sang `LocalExecutor` và Postgres cho Airflow. Hàng đợi trong PostgreSQL cùng worker dùng chung image backend cho cùng kết quả mà không thêm hạ tầng. APScheduler 4 vẫn là bản alpha và dễ tạo scheduler trùng khi chạy nhiều worker uvicorn; Procrastinate chưa xác nhận hỗ trợ Python 3.14.

## Hàng đợi

Bảng `technical.text2sql_ingestion_jobs` (xem [dữ liệu](du-lieu.md)). Mỗi job là một cặp `(connection_id, topic)`.

- **Gộp job.** Chỉ số unique có điều kiện `status = 'pending'` trên `(connection_id, topic)`. Ghi job dùng `ON CONFLICT DO NOTHING`, nên nhiều thay đổi liên tiếp chỉ tạo một job chờ. Job chạy sau sẽ đọc dữ liệu mới nhất.
- **Lấy job.** `SELECT … FOR UPDATE SKIP LOCKED` nên nhiều worker không lấy trùng. Job không được lấy khi cùng `(connection_id, topic)` đang chạy; thay đổi đến trong lúc đó tạo một job chờ mới, chạy ngay sau khi job hiện tại xong.
- **Retry.** Lỗi thì job về `pending` với `run_after` lùi theo cấp số nhân (30 giây, 60 giây, … tối đa 15 phút) cho đến `TEXT2SQL_JOB_MAX_ATTEMPTS`, sau đó `failed`. Nếu lúc lỗi đã có job chờ mới thì job cũ thành `superseded`. `last_error` chỉ ghi mã lỗi nghiệp vụ hoặc tên lớp exception, không ghi thông điệp gốc để không lộ secret.
- **Job treo.** Job `running` quá `TEXT2SQL_JOB_TIMEOUT_SECONDS` được đưa về hàng đợi (tính vào số lần thử).
- **Dọn dẹp.** Job đã kết thúc quá `TEXT2SQL_JOB_RETENTION_DAYS` ngày bị xóa, kiểm tra mỗi giờ.

## Ba nguồn tạo job

| `source` | Khi nào |
| --- | --- |
| `event` | Trigger: người dùng thay đổi dữ liệu. |
| `manual` | `POST /api/v1/text2sql/ingestion/jobs`, dùng cho nút "Ingest lại". Xem [API job](api-ingestion-jobs.md). |
| `schedule` | Worker tự phát lịch theo chu kỳ riêng của từng topic. |

### Trigger khi dữ liệu đổi

`ingestion/triggers.py` đăng ký listener `after_flush` của SQLAlchemy lúc backend khởi động. Khi một flush có thay đổi ở model được theo dõi, listener xác định `connection_id` rồi ghi job vào hàng đợi **trong cùng transaction**: commit thì job có, rollback thì không, không mất sự kiện và không phải sửa từng service.

| Thay đổi ở | Topic được xếp job |
| --- | --- |
| Schema, bảng, cột, từ điển bảng/cột, từ đồng nghĩa | Tất cả topic (tên bảng, cột có mặt trong văn bản của mọi topic) |
| Metric | `metric`, `glossary`, `expert_rule`, `own_knowledge` |
| Thuật ngữ, revision, liên kết thuật ngữ | `glossary`, `expert_rule`, `own_knowledge` |
| Quy tắc, revision, liên kết quy tắc | `expert_rule`, `own_knowledge` |
| Mục tri thức riêng | `own_knowledge` |

Tra `connection_id` được ghi nhớ trong từng lần flush, nên đồng bộ metadata hàng nghìn cột không sinh hàng nghìn truy vấn. Listener thiên về xếp thừa hơn thiếu: job thừa chỉ tốn đọc PostgreSQL vì `content_hash` giúp bỏ qua việc embed. Đối tượng bị xóa cùng cha (cascade) không tra được connection nên không xếp job; lịch định kỳ bên dưới bù cho các trường hợp này. Thay đổi ghi bằng SQL thô hoặc ngoài backend cũng chỉ được bù bằng lịch.

### Lịch định kỳ

Mỗi topic có chu kỳ riêng, worker chỉ tạo job `schedule` cho connection đang hoạt động chưa có job `schedule` nào của topic đó trong 90% chu kỳ. Nhiều worker cùng chạy vẫn không tạo trùng nhờ điều kiện này và chỉ số gộp job.

| Topic | Chu kỳ mặc định |
| --- | ---: |
| `table`, `column` | 900 giây |
| `metric`, `glossary`, `expert_rule` | 300 giây |
| `own_knowledge` | 120 giây |

Đổi bằng `TEXT2SQL_TOPIC_INTERVALS`, ví dụ `metric=60,own_knowledge=45`; mỗi giá trị tối thiểu 30 giây, topic hoặc giá trị sai làm worker không khởi động.

## Chạy song song

Worker dùng thread pool tối đa `TEXT2SQL_WORKER_CONCURRENCY` job cùng lúc (mặc định 4). Mỗi job mở session và client riêng. Các topic của cùng một connection chạy song song được vì mỗi topic ghi point khác nhau và xóa point cũ chỉ trong topic của mình. Khi nhận SIGTERM, worker ngừng lấy job mới và chờ job đang chạy; Compose cho `stop_grace_period` 90 giây.

## Cấu hình

| Biến | Mặc định | Ý nghĩa |
| --- | ---: | --- |
| `TEXT2SQL_WORKER_CONCURRENCY` | 4 | Số job chạy song song. |
| `TEXT2SQL_WORKER_POLL_SECONDS` | 2 | Chu kỳ worker kiểm tra hàng đợi. |
| `TEXT2SQL_JOB_MAX_ATTEMPTS` | 3 | Số lần thử tối đa của một job. |
| `TEXT2SQL_JOB_TIMEOUT_SECONDS` | 900 | Sau thời gian này job `running` bị coi là treo. |
| `TEXT2SQL_JOB_RETENTION_DAYS` | 7 | Số ngày giữ job đã kết thúc. |
| `TEXT2SQL_TOPIC_INTERVALS` | trống | Ghi đè chu kỳ lịch theo topic. |

Worker cần cùng `DATABASE_URL`, `QDRANT_URL`, `OPENROUTER_API_KEY` với backend. Compose dùng chung một khối biến môi trường cho hai service và chỉ khởi động worker sau khi backend khỏe, tức là sau khi `alembic upgrade head` xong.

## Giới hạn hiện tại

- Chưa có giao diện xem job; xem qua `GET /api/v1/text2sql/ingestion/jobs`.
- Point của connection đã bị xóa vẫn còn trong Qdrant vì job không còn connection để đồng bộ.
- Nếu mọi worker dừng, job vẫn nằm trong hàng đợi và được xử lý khi worker chạy lại.
