# API lượt hỏi đáp

**Trạng thái:** đã triển khai tại `/api/v1/conversations/{id}/turns`. Không có route tạo lượt: lượt do pipeline chat ghi qua service ([ghi lượt từ pipeline](ghi-luot-tu-pipeline.md)).

| Method | Path | Hành vi |
| --- | --- | --- |
| GET | `/{id}/turns?user_id=...` | Liệt kê lượt theo `sequence` tăng dần; `limit` (1–500, mặc định 100), `offset`. |
| GET | `/{id}/turns/{turn_id}?user_id=...` | Một lượt. |
| DELETE | `/{id}/turns/{turn_id}?user_id=...` | Xóa lượt và đánh giá của nó; lượt thử lại trỏ tới lượt này có `retry_of` về `null`; trả 204. |
| PUT | `/{id}/turns/{turn_id}/views/{result_id}` | Lưu biểu đồ người dùng chọn cho một kết quả. Body `{user_id, chart}`; trả `{result_id, chart (đã chuẩn hóa), warnings, updated_at}`. |
| DELETE | `/{id}/turns/{turn_id}/views/{result_id}?user_id=...` | Bỏ lựa chọn, quay về biểu đồ của agent; trả 204 (không có lựa chọn cũng 204). |

Hội thoại không thuộc `user_id` trả 404 `Không tìm thấy hội thoại.`; lượt không thuộc hội thoại trả 404 `Không tìm thấy lượt hỏi đáp.` Xóa lượt không đánh lại `sequence` của các lượt còn lại.

## Dạng một lượt

`id`, `conversation_id`, `sequence`, `question`, `rewritten_question`, `answer`, `flow`, `status`, `steps`, `results`, `rewrite`, `assumptions`, `pii`, `dataset_id`, `retry_of`, `continued_from`, `clarification_question`, `clarification_options` (luôn là danh sách), `resume_id`, `resume_expires_at`, `error_code`, `error`, `duration_ms`, `model`, `feedback`, `views`, `created_at`, `updated_at`. Cấu trúc `steps`, `results`, `rewrite` do route chat ghi, xem [dữ liệu route chat lưu](ghi-luot-tu-pipeline.md#dữ-liệu-route-chat-lưu). Lượt ghi trước ngày 2026-11-19 có cấu trúc của pipeline cũ (bước `join_plan`, `pii`...).

- `error` là thông điệp chung `AI Agent không hoàn tất được câu trả lời.` khi `status` là `error`, ngược lại `null`. `error_message` và `continuation` nội bộ **không bao giờ** có trong response.
- `resume_id` và `resume_expires_at` lấy từ `continuation` của lượt `needs_clarification` (hoặc `join_ambiguous`) còn hạn, để giao diện chạy tiếp một lượt đang chờ sau khi tải lại trang; lượt khác hoặc đã hết hạn thì cả hai là `null`. Lượt đã được trả lời rồi vẫn giữ `resume_id` cũ, nhưng gửi lại thì route chat trả 404 vì checkpoint đã bị xóa; giao diện chỉ dùng `resume_id` của lượt cuối.
- `results` là dữ liệu route chat đã gửi cho client (giá trị thật; dữ liệu cá nhân chỉ được che khi gửi LLM, xem [ghi lượt từ pipeline](ghi-luot-tu-pipeline.md#dữ-liệu-và-pii)); mỗi mục có `stored_truncated` cho biết số dòng lưu bị cắt theo `CONVERSATION_MAX_STORED_ROWS` (khác `truncated` là cắt khi chạy truy vấn).
- `feedback` là đánh giá của chính `user_id` (`rating`, `comment`, `created_at`, `updated_at`) hoặc `null`.
- `results` được chuẩn hóa khi đọc (`normalize_results` ở `services/result_views.py`, không ghi lại database): mục đã có `result_id` giữ nguyên; mục cũ (ghi trước khi có biểu đồ) được gán `result_id` = `"<position>-<k>"` (đếm theo `position`, bỏ qua mục `column_values`), `fields` đoán từ giá trị (`infer_fields`), `chart_types` tính lại, `chart = null`, `chart_source = null`, `display = "none"`.
- `views` là `{result_id: {chart, updated_at}}` hoặc `null`: biểu đồ người dùng đã chọn; frontend ưu tiên `views[result_id].chart` hơn `chart` của kết quả.

## Lựa chọn biểu đồ (`views`)

`PUT .../views/{result_id}`: `result_id` theo mẫu `^\d+-\d+$` (tối đa 32 ký tự, sai thì 422). Service khóa dòng hội thoại (`get_owned(lock=True)`, `SELECT ... FOR UPDATE`) để hai lần lưu đồng thời trên cùng lượt không ghi đè nhau, tìm kết quả trong `results` đã chuẩn hóa (không có thì 404 `conversation_result_not_found`), kiểm spec bằng `validate_chart` của [biểu đồ](../text2sql/bieu-do.md) trên `fields` và các dòng đã lưu (sai thì 400 `conversation_chart_invalid`, `detail` là các thông báo nối bằng xuống dòng). Kết quả có `stored_truncated` hoặc `truncated` thì các quy tắc theo dữ liệu chỉ thành cảnh báo trong `warnings`. Mỗi lần lưu gán một dict `views` mới (không sửa tại chỗ) nên các lựa chọn của kết quả khác được giữ. Hội thoại hoặc lượt không thuộc `user_id` trả 404 như các route khác.

Lượt chạy tiếp sau hỏi lại là lượt mới: lựa chọn biểu đồ trên lượt cũ không tự chuyển sang lượt mới.
