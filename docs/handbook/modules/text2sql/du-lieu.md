# Dữ liệu của text2sql

**Trạng thái:** migration `d3b7f19a5e24` (thư mục `init_text2sql_module`) đã triển khai sau `own_knowledge`.

Qdrant chứa chỉ mục tìm kiếm có thể tạo lại; nguồn dữ liệu gốc vẫn là các module khác. PostgreSQL có hai bảng kỹ thuật của module này: hàng đợi ingestion (mô tả dưới đây) và `technical.text2sql_query_datasets` (migration `7e4c1a9b5d32`, định nghĩa join dùng lại của `query_dataset`, xem [dataset truy vấn](query-datasets.md)).

## Schema `technical`

Bảng hạ tầng kỹ thuật (hàng đợi, trạng thái chạy nền) nằm trong schema PostgreSQL riêng `technical`, tách khỏi bảng nghiệp vụ. Hằng `TECHNICAL_SCHEMA` ở `backend/common/base_model.py`; bảng kỹ thuật mới khai báo `{"schema": TECHNICAL_SCHEMA}` trong `__table_args__`. Migration `d3b7f19a5e24` tạo schema bằng `CREATE SCHEMA IF NOT EXISTS technical`; downgrade xóa bảng rồi xóa schema nếu trống.

`backend/migrations/env.py` bật `include_schemas` kèm bộ lọc `backend/common/migration.py` chỉ nhìn schema mặc định và `technical`, nếu không `alembic check` sẽ luôn báo thiếu bảng. Tên index tự sinh từ `index=True` có chèn tên schema (`ix_technical_<bảng>_<cột>`); migration phải dùng đúng tên đó. Tên ràng buộc CHECK chỉ truyền phần ngắn (`status_valid`), quy ước đặt tên tự thêm tiền tố.

SQLite chỉ dùng cho test không có schema; `ingestion_job.py` gắn một database trong bộ nhớ tên `technical` vào mỗi kết nối SQLite. Khóa ngoại sang bảng ở schema chính không hoạt động trên SQLite, nên test migration so sánh metadata bỏ qua bảng thuộc `technical`; ràng buộc này được kiểm chứng trên PostgreSQL.

## `technical.text2sql_ingestion_jobs`

| Cột | Ý nghĩa |
| --- | --- |
| `id`, `created_at`, `updated_at` | Từ `BaseModel` (UUID v7). |
| `connection_id` | Khóa ngoại tới `database_connections`, `ON DELETE CASCADE`. |
| `topic` | Một trong `table`, `column`, `metric`, `glossary`, `expert_rule`, `own_knowledge`. |
| `source` | `event`, `schedule` hoặc `manual`. |
| `status` | `pending`, `running`, `succeeded`, `failed`, `superseded`. |
| `attempts` | Số lần đã lấy để chạy. |
| `run_after` | Không lấy job trước thời điểm này (dùng cho retry). |
| `started_at`, `finished_at` | Thời gian chạy. |
| `last_error` | Mã lỗi nghiệp vụ hoặc tên lớp exception, tối đa 1000 ký tự. |
| `result` | JSON `total`, `indexed`, `unchanged`, `deleted`, `seconds` khi thành công. |

Chỉ mục: `uq_text2sql_ingestion_jobs_pending` unique trên `(connection_id, topic)` với điều kiện `status = 'pending'` (gộp job chờ); `ix_text2sql_ingestion_jobs_claim` trên `(status, run_after)` cho việc lấy job; `ix_technical_text2sql_ingestion_jobs_connection_id`. Cơ chế vận hành ở [worker và hàng đợi](worker-ingestion.md).
