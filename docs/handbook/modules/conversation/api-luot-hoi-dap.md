# API lượt hỏi đáp

**Trạng thái:** đã triển khai tại `/api/v1/conversations/{id}/turns`. Không có route tạo lượt: lượt do pipeline chat ghi qua service ([ghi lượt từ pipeline](ghi-luot-tu-pipeline.md)).

| Method | Path | Hành vi |
| --- | --- | --- |
| GET | `/{id}/turns?user_id=...` | Liệt kê lượt theo `sequence` tăng dần; `limit` (1–500, mặc định 100), `offset`. |
| GET | `/{id}/turns/{turn_id}?user_id=...` | Một lượt. |
| DELETE | `/{id}/turns/{turn_id}?user_id=...` | Xóa lượt và đánh giá của nó; lượt thử lại trỏ tới lượt này có `retry_of` về `null`; trả 204. |

Hội thoại không thuộc `user_id` trả 404 `Không tìm thấy hội thoại.`; lượt không thuộc hội thoại trả 404 `Không tìm thấy lượt hỏi đáp.` Xóa lượt không đánh lại `sequence` của các lượt còn lại.

## Dạng một lượt

`id`, `conversation_id`, `sequence`, `question`, `rewritten_question`, `answer`, `flow`, `status`, `steps`, `results`, `rewrite`, `assumptions`, `pii`, `dataset_id`, `retry_of`, `continued_from`, `clarification_question`, `clarification_options` (luôn là danh sách), `error_code`, `error`, `duration_ms`, `model`, `feedback`, `created_at`, `updated_at`. Cấu trúc `steps`, `results`, `pii` do pipeline chat ghi, xem [luồng chat](../text2sql/chat-flow.md#dữ-liệu-một-lượt); với lượt `join_ambiguous`, bước `join_plan` trong `steps` có `options[].signature` để client cho người dùng chọn cách nối.

- `error` là thông điệp chung `AI Agent không hoàn tất được câu trả lời.` khi `status` là `error`, ngược lại `null`. `error_message` và `continuation` nội bộ **không bao giờ** có trong response.
- `results` là dữ liệu đã che PII; mỗi mục có `stored_truncated` cho biết số dòng lưu bị cắt theo `CONVERSATION_MAX_STORED_ROWS` (khác `truncated` là cắt khi chạy truy vấn).
- `feedback` là đánh giá của chính `user_id` (`rating`, `comment`, `created_at`, `updated_at`) hoặc `null`.
