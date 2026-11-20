# Dữ liệu của text2sql

**Trạng thái:** migration `d3b7f19a5e24` (thư mục `init_text2sql_module`) đã triển khai sau `own_knowledge`; migration `e8b2c6d4f170` (sau `4d8a1c7e3b92`) tạo `technical.text2sql_chat_checkpoints` ngày 2026-11-20; migration `a7d3e9c2b415` (sau `f4b8d2a6c913`) thêm cột `masked_values`.

Qdrant chứa chỉ mục tìm kiếm có thể tạo lại; nguồn dữ liệu gốc vẫn là các module khác. PostgreSQL có hai bảng kỹ thuật đang dùng của module này: hàng đợi ingestion và checkpoint của lượt chat đang chờ hỏi lại (mô tả dưới đây). Bảng `technical.text2sql_query_datasets` (migration `7e4c1a9b5d32`, định nghĩa join dùng lại của `query_dataset` cũ) vẫn còn trong database nhưng không còn model hay code dùng, vì phần hỏi đáp đã gỡ ngày 2026-11-19.

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

## `technical.text2sql_chat_checkpoints`

Checkpoint LangGraph của một lượt chat đang dừng chờ người dùng trả lời câu hỏi lại; cách dùng ở [hỏi lại và chạy tiếp](api-chat.md#hỏi-lại-và-chạy-tiếp). Model `ChatCheckpoint`, repository `ChatCheckpointRepository`.

| Cột | Ý nghĩa |
| --- | --- |
| `id` | `resume_id` trả cho client, cũng là `thread_id` của graph. UUID v4 sinh ngẫu nhiên (không dùng UUID v7 mặc định) vì ở chế độ không có `user_id` đây là khóa duy nhất để chạy tiếp. |
| `created_at`, `updated_at` | Từ `BaseModel`. |
| `connection_id` | Khóa ngoại tới `database_connections`, `ON DELETE CASCADE`. |
| `user_id` | Người hỏi; `null` khi request không có `user_id`. |
| `conversation_id` | Khóa ngoại tới `conversations`, `ON DELETE CASCADE`; `null` khi không lưu hội thoại. |
| `turn_id` | Khóa ngoại tới `conversation_turns` (lượt `needs_clarification` đang chờ), `ON DELETE CASCADE`. |
| `snapshot` | `bytea`: checkpoint, writes và blobs của thread do `SnapshotSaver.export_thread` đóng gói bằng msgpack của LangGraph. Chứa state của graph: kết quả tiền xử lý, câu trả lời và dòng dữ liệu của các câu đã xong, messages của agent đang chờ (chưa che PII, giống response). Không chứa bản nháp hay delta của stream chữ; cờ `streaming` và các callback stream nằm trong context của graph (`ChatGraphContext`, `ToolAgentContext`), không nằm trong state, nên snapshot tạo trước khi có stream chữ vẫn chạy tiếp được. |
| `masked_values` | JSON, null: bảng nhãn thay thế -> giá trị thật của lượt đang chờ (xem [che dữ liệu cá nhân](api-chat.md#che-dữ-liệu-cá-nhân)); chứa dữ liệu cá nhân thật nên chỉ tồn tại tới khi dòng bị xóa. `null` khi lượt không che gì. |
| `expires_at` | Hết hạn sau `TEXT2SQL_CLARIFICATION_TTL_MINUTES`; dòng hết hạn bị coi như không có và bị xóa mỗi khi lưu checkpoint mới. |

Chỉ mục: `ix_technical_text2sql_chat_checkpoints_connection_id`, `..._conversation_id`, `..._expires_at`. Dòng bị xóa khi lượt được chạy tiếp (transaction cùng `begin_turn`) và ghi lại nếu lần chạy tiếp lỗi. Không có job dọn riêng: dòng hết hạn chỉ bị xóa khi có lượt mới dừng; có thể xóa tay `DELETE FROM technical.text2sql_chat_checkpoints WHERE expires_at <= now()` bất cứ lúc nào.
