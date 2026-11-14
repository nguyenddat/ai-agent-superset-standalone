# API AI Agent push và đọc kho riêng

**Trạng thái:** đã triển khai tại `/api/v1/own-knowledge`; cần header `X-Own-Knowledge-Key: <OWN_KNOWLEDGE_AGENT_KEY>`.

| Method | Path | Hành vi |
| --- | --- | --- |
| POST | `/clarifications` | Đẩy một lượt hỏi lại và phương án; idempotent theo khóa của Agent. |
| GET | `/clarifications/{id}?user_id=...` | Đọc lại lượt hỏi của đúng người dùng. |
| POST | `/clarifications/{id}/answer` | Ghi xác nhận hoặc bỏ qua; chỉ xác nhận mới cập nhật kho riêng. |
| GET | `/agent/entries?connection_id=...&user_id=...` | Đọc các cách hiểu riêng còn hoạt động cho Agent. |
| PUT | `/agent/entries/{id}` | Người dùng sửa cách hiểu qua Agent, tăng version và mở lại review. |
| DELETE | `/agent/entries/{id}?user_id=...` | Xóa cách hiểu riêng của người dùng. |

Body push cần `user_id`, `connection_id`, `idempotency_key`, `question`, `missing` và `proposals`; có thể kèm `source_session_id`, `source_question_id`. `missing` là các loại `glossary`, `metric`, `expert_rule`. Mỗi proposal gồm `kind`, `name`, `prompt`, `options` (1–10 chuỗi), có thể kèm `concept` và `table_id`. Proposal phải thuộc loại có trong `missing`; bảng phải thuộc connection. Agent tạo `idempotency_key` ổn định cho một lượt hỏi để retry không nhân đôi.

Body answer gồm `user_id`, `state` là `confirmed` hoặc `dismissed`, và `answers`. Với `confirmed`, mỗi answer chọn đúng một `proposal_id` cùng `option_index` hoặc nhập `definition` riêng. `dismissed` yêu cầu mảng `answers` rỗng. Một câu hỏi chỉ được trả lời một lần; API ghi các mục confirmed theo `(user_id, connection_id, kind, tên chuẩn hóa)` và trả danh sách đã ghi.

`GET /agent/entries` chỉ trả mục riêng chưa có bản hệ thống đang phục vụ. API không tự chạy mô hình AI hoặc tự chứng minh khái niệm còn thiếu; Agent phải so với catalog hệ thống trước khi push và ưu tiên ngữ nghĩa hệ thống khi dùng kết quả. API cũng không xác thực trực tiếp người dùng cuối: dịch vụ Agent giữ khóa bí mật và truyền `user_id` lấy từ phiên đăng nhập của mình.
