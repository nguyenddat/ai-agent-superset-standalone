# Dữ liệu conversation

**Trạng thái:** đã triển khai, revision `a4c2e8f61b37` (thư mục `init_conversation_module`, `down_revision` là `7e4c1a9b5d32`) tạo ba bảng; revision `c5e1d7a3b902` (`down_revision` `a4c2e8f61b37`, 2026-11-16) thêm bốn cột vào `conversation_turns`, viết bằng `batch_alter_table` để chạy được cả trên SQLite của test (trên PostgreSQL là các lệnh `ALTER TABLE` thường); đã kiểm tra upgrade, `alembic check`, downgrade trên PostgreSQL tạm. Revision `f4b8d2a6c913` (`down_revision` `e8b2c6d4f170`, 2026-11-20) thêm cột `views` vào `conversation_turns`, cũng bằng `batch_alter_table`; test kiểm upgrade và downgrade trên SQLite. Model ở `backend/modules/conversation/models/conversation.py`, kế thừa `BaseModel` (UUID v7, `created_at`, `updated_at`). JSON dùng `sqlalchemy.JSON` như các module khác.

## `conversations`

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| `connection_id` | UUID | FK `database_connections.id`, `ON DELETE CASCADE`, có index. |
| `user_id` | `String(255)` | Do client cung cấp, chưa xác thực; có index. |
| `title` | `String(200)` | Mặc định rỗng; đặt từ câu hỏi đầu khi có lượt đầu nếu còn rỗng. |
| `is_pinned`, `is_archived` | boolean | Mặc định `false`. |
| `last_message_at` | timestamptz, null | Cập nhật khi bắt đầu và kết thúc lượt; có index. |

Index `ix_conversations_owner_recent` trên `(user_id, connection_id, last_message_at)` phục vụ danh sách theo người dùng.

## `conversation_turns`

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| `conversation_id` | UUID | FK `conversations.id`, `ON DELETE CASCADE`, có index. |
| `sequence` | int | Tăng dần từ 1 trong hội thoại; `uq_conversation_turn_sequence` trên `(conversation_id, sequence)`. |
| `question`, `rewritten_question`, `answer` | text | Câu hỏi gốc, câu đã viết lại, câu trả lời. |
| `flow` | `String(16)`, null | CHECK `ck_conversation_turns_flow_valid`: `metric`, `dataset`, `none`. |
| `status` | `String(24)` | CHECK `ck_conversation_turns_status_valid`: `running`, `answered`, `needs_clarification`, `cannot_answer`, `join_ambiguous`, `join_not_declared`, `error`. `running` là lượt đang chạy hoặc bị ngắt giữa chừng. |
| `steps` | JSON, null | Mỗi câu đơn và các bước công cụ của agent (không có dòng dữ liệu); xem [dữ liệu route chat lưu](ghi-luot-tu-pipeline.md#dữ-liệu-route-chat-lưu). Lượt cũ có dạng `{step, status, detail, reasoning}` của pipeline đã gỡ. |
| `results` | JSON, null | Danh sách kết quả truy vấn (`kind`, `sql`, `columns`, `rows` như đã gửi client, `row_count`, `truncated`, …) cùng `stored_truncated`. Route chat chỉ che dữ liệu cá nhân khi gửi LLM, `rows` lưu là giá trị thật. |
| `rewrite`, `assumptions`, `pii` | JSON, null | Kết quả tiền xử lý (câu viết lại, các câu đơn, loại câu hỏi, metric truy hồi), giả định, thông tin che PII. Route chat để trống `assumptions`; `pii` là `{"history_answer": ...}` khi câu trả lời có dữ liệu cá nhân (bản còn nhãn thay thế cho bước viết lại câu hỏi), ngược lại `null`. |
| `dataset_id` | UUID, null | Tham chiếu mềm tới `technical.text2sql_query_datasets`; không đặt FK vì khác schema và test SQLite. |
| `retry_of` | UUID, null | FK tự tham chiếu, `ON DELETE SET NULL`, có index. |
| `error_code` | `String(64)`, null | Mã lỗi trả ra API. |
| `error_message` | text, null | Nguyên nhân nội bộ, không trả ra API. |
| `duration_ms`, `model` | int, `String(100)` | Thời gian xử lý và mô hình đã dùng. |
| `clarification_question` | text, null | Câu hỏi làm rõ (đã làm sạch UUID) khi lượt cần làm rõ; đưa vào lịch sử cho lượt sau. |
| `clarification_options` | JSON, null | Tối đa 4 lựa chọn trả lời ngắn; API trả `[]` khi không có. |
| `continued_from` | UUID, null | FK tự tham chiếu `fk_conversation_turns_continued_from_conversation_turns`, `ON DELETE SET NULL`, index `ix_conversation_turns_continued_from`: lượt `join_ambiguous` mà lượt này tiếp tục. |
| `views` | JSON, null | `{result_id: {chart, updated_at}}`: biểu đồ người dùng chọn cho từng kết quả, ghi qua [API lượt hỏi đáp](api-luot-hoi-dap.md#lựa-chọn-biểu-đồ-views). |
| `continuation` | JSON, null | Lượt `needs_clarification` của route chat text2sql: `kind = text2sql_clarification`, `resume_id`, `expires_at` (checkpoint ở `technical.text2sql_chat_checkpoints`). Trạng thái tiếp tục của lượt `join_ambiguous` (kế hoạch dataset đã ánh xạ, `table_ids`, `root_table_id`, câu đã viết lại, giả định, lý do, các signature); nội bộ, API không trả. |

## `conversation_turn_feedback`

| Cột | Kiểu | Ghi chú |
| --- | --- | --- |
| `turn_id` | UUID | FK `conversation_turns.id`, `ON DELETE CASCADE`, có index. |
| `user_id` | `String(255)` | Người đánh giá (chủ hội thoại). |
| `rating` | `String(8)` | CHECK `ck_conversation_turn_feedback_rating_valid`: `up`, `down`. |
| `comment` | text, null | Tối đa 2000 ký tự (kiểm tra ở API). |

`uq_conversation_turn_feedback_user` trên `(turn_id, user_id)`: mỗi người một đánh giá cho mỗi lượt; ghi lại là cập nhật.

## Cấu hình

`CONVERSATION_MAX_STORED_ROWS` (mặc định 200, 1–5000): số dòng tối đa lưu cho mỗi truy vấn trong `results`.
