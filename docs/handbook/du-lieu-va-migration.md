# Dữ liệu và migration

## Hai loại database

1. **Metadata database của ứng dụng:** `DATABASE_URL` trong `.env` hoặc biến môi trường. Backend dùng `backend.core.setting.Config` và `backend.core.database` để mở session. Alembic chỉ chạy trên database này.
2. **Database nguồn:** người dùng đăng ký để đọc metadata và dữ liệu. Thông tin kết nối nằm trong `database_connections.uri_ciphertext`; schema, bảng và cột được đồng bộ vào các bảng metadata của ứng dụng.

`DATABASE_URL` không được trỏ đến database nguồn chỉ để thử kết nối. Không chạy Alembic trên database nguồn.

Service đăng ký database nguồn dùng `CONNECTION_ENCRYPTION_KEY` (khóa Fernet) để mã hóa URI trước khi lưu. Tạo khóa bằng `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` rồi đặt trong `.env` hoặc secret manager. Không lưu khóa trong Git; sao lưu khóa an toàn vì mất khóa sẽ không đọc được các URI đã mã hóa.

## Cấu trúc Alembic

`alembic.ini` ở gốc repository, script nằm trong `backend/migrations/`. Revision đầu tiên là baseline; mỗi module có thư mục `backend/migrations/versions/init_<ten_module>_module/`. Module `database_connection` dùng `init_database_module`, `data_dictionary` dùng `init_data_dictionary_module`, `business_model` dùng `init_business_model_module`, `data_lineage` dùng `init_data_lineage_module`, `metric_management` dùng `init_metric_management_module`, `glossary_management` dùng `init_glossary_management_module`, `expert_rule_management` dùng `init_expert_rule_management_module`, `own_knowledge` dùng `init_own_knowledge_module`, `text2sql` dùng `init_text2sql_module`, `conversation` dùng `init_conversation_module` (revision `a4c2e8f61b37` sau `7e4c1a9b5d32`, tạo `conversations`, `conversation_turns`, `conversation_turn_feedback`; revision `c5e1d7a3b902` sau `a4c2e8f61b37` thêm `clarification_question`, `clarification_options`, `continued_from`, `continuation` vào `conversation_turns`, là head hiện tại; xem [dữ liệu conversation](modules/conversation/du-lieu.md)). `version_locations` trong `alembic.ini` liệt kê các thư mục này. Các revision đầu của `database_connection` lần lượt tạo connection, schema, table và column.

```powershell
uv sync
$env:DATABASE_URL = "postgresql+psycopg://app:password@localhost:5432/ai_agent"
uv run alembic upgrade head
uv run alembic check
```

Khi thêm bảng: viết model, import model trong `models/__init__.py` và bảo đảm `backend/migrations/env.py` import package model; tạo revision ở đúng thư mục bằng `--version-path`, xem lại script trước khi chạy upgrade. Không dùng `Base.metadata.create_all()` trong startup để thay Alembic.

## Schema kỹ thuật

Bảng hạ tầng kỹ thuật (hàng đợi, trạng thái tác vụ nền) đặt trong schema PostgreSQL `technical`, không lẫn với bảng nghiệp vụ ở schema mặc định. Khai báo `{"schema": TECHNICAL_SCHEMA}` (từ `backend.common.base_model`) trong `__table_args__` và để migration chạy `CREATE SCHEMA IF NOT EXISTS technical` trước khi tạo bảng. `env.py` bật `include_schemas` với bộ lọc ở `backend/common/migration.py`, nên `alembic check` nhìn được cả schema này. Khi autogenerate hoặc viết tay, kiểm tra tên index tự sinh (có chèn tên schema) và đặt tên CHECK ngắn để quy ước đặt tên không lặp tiền tố. Hiện có `technical.text2sql_ingestion_jobs` (xem [dữ liệu text2sql](modules/text2sql/du-lieu.md)) và `technical.text2sql_query_datasets` (revision `7e4c1a9b5d32`, lưu định nghĩa join dùng lại của `query_dataset`, xem [dataset truy vấn](modules/text2sql/query-datasets.md)).

## Khóa và thời gian

`BaseModel` cung cấp UUID v7, `created_at` và `updated_at`; `AuditedModel` thêm `created_by_id`, `updated_by_id` nullable. Bốn bảng của module `database_connection` kế thừa `BaseModel`; các model của `data_dictionary` và `business_model` kế thừa `AuditedModel` vì do người dùng chỉnh sửa. Bảng ghép `business_domain_tables` dùng khóa chính gồm hai khóa ngoại, không có cột audit. Revision chuyển đổi sau bốn script tạo bảng đổi ID và khóa ngoại số nguyên sang UUID v7, giữ metadata và quan hệ. Downgrade đánh lại ID số nguyên; không thể khôi phục giá trị số nguyên ban đầu.

Thời gian lưu trong cột timezone-aware theo UTC. Formatter ở `common` xuất thời gian thành ISO 8601 UTC có hậu tố `Z`. Các giá trị `last_synced_at` là thời điểm metadata được lấy từ database nguồn, không phải thời điểm dữ liệu nghiệp vụ của bảng nguồn thay đổi.
