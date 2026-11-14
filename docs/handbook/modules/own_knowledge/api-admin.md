# API admin review và chuyển thành hệ thống

**Trạng thái:** đã triển khai tại `/api/v1/own-knowledge`; cần header `X-Own-Knowledge-Key: <OWN_KNOWLEDGE_ADMIN_KEY>`.

| Method | Path | Hành vi |
| --- | --- | --- |
| GET | `/admin/entries` | Danh sách mọi mục riêng; lọc được theo `connection_id`, `status`, `user_id`. |
| GET | `/admin/entries/{id}` | Đọc chi tiết, gồm câu hỏi nguồn. |
| POST | `/admin/entries/{id}/review` | `keep_own` hoặc `reopen`; lưu note, reviewer và tăng version. |
| POST | `/admin/entries/{id}/promote` | Tạo glossary, metric hoặc expert rule hệ thống trong cùng transaction. |

Body review gồm `expected_version`, `action`, `reviewer_id`, tùy chọn `note`. Body promote gồm `expected_version`, `target_kind`, `payload`, `reviewer_id`, tùy chọn `note`. `expected_version` phải khớp bản admin vừa đọc, nếu không trả 409. Khóa Agent không truy cập được route admin.

`payload` được kiểm tra bằng schema của module đích. Với glossary cần `canonical_name`, `definition` và các liên kết tùy chọn. Với metric cần `table_id`, `name`, `expression`; bảng phải thuộc connection của mục riêng. Với expert rule cần `table_id`, `name`, `conditions`, `glossary_term_ids` cùng các trường tùy chọn. `connection_id` của glossary/rule luôn do server lấy từ mục riêng, không tin giá trị do client gửi. Admin cần kiểm tra nội dung, nhất là biểu thức metric, trước khi gọi promote. Không có bước tự động biến câu trả lời người dùng thành SQL hoặc rule đã duyệt.

Promotion tạo glossary/rule ở trạng thái draft; admin dùng API của module đó để duyệt. Trong thời gian chờ duyệt, Agent vẫn nhận tri thức riêng. Metric tạo thủ công đang hoạt động ngay sau promotion vì module metric hiện chưa có vòng đời duyệt. `reviewer_id` là ID từ hệ thống admin gọi API; khóa dịch vụ xác thực hệ thống gọi, chưa xác thực riêng từng admin trong standalone.
