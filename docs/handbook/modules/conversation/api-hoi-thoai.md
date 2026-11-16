# API hội thoại

**Trạng thái:** đã triển khai tại `/api/v1/conversations` (tag `conversations`), route ở `backend/modules/conversation/routes/router_conversation.py`. Không có khóa dịch vụ; `user_id` chưa được xác thực (xem quy tắc sở hữu ở [tổng quan](README.md)).

| Method | Path | Hành vi |
| --- | --- | --- |
| POST | gốc (không có `/` cuối) | Tạo hội thoại `{connection_id, user_id, title?}`; trả 201. |
| GET | gốc `?user_id=...` | Liệt kê hội thoại của người dùng. |
| GET | `/{id}?user_id=...` | Chi tiết kèm các lượt. |
| PATCH | `/{id}` | Sửa `{user_id, title?, is_pinned?, is_archived?}`. |
| DELETE | `/{id}?user_id=...` | Xóa hội thoại, các lượt và đánh giá; trả 204. |

## Tạo

`connection_id` phải tồn tại, nếu không trả 404 `Kết nối dữ liệu không tồn tại.` `title` bỏ trống thì lưu chuỗi rỗng và được đặt từ câu hỏi đầu tiên khi pipeline ghi lượt đầu (`title_from_question`: gọn khoảng trắng, cắt tối đa 80 ký tự ở ranh giới từ, thêm `…`). Nếu gửi `title`, tiêu đề được gọn khoảng trắng; rỗng hoặc dài hơn 200 ký tự trả 400.

## Liệt kê

Query: `user_id` (bắt buộc), `connection_id` (lọc; connection không tồn tại trả 404), `archived` (mặc định `false`, chỉ trả hội thoại đúng trạng thái lưu trữ), `q` (tìm trong tiêu đề, không phân biệt hoa thường, `%` và `_` được hiểu theo nghĩa đen), `limit` (1–200, mặc định 50), `offset`.

Thứ tự: hội thoại ghim trước, rồi `last_message_at` giảm dần (hội thoại chưa có lượt nằm cuối), rồi `created_at` giảm dần. Mỗi mục có các trường hội thoại, `turn_count`, `last_question` (câu hỏi lượt cuối, cắt ở 120 ký tự) và `last_status`.

## Chi tiết

Trả các trường hội thoại, `turn_count` và `turns` theo `sequence` tăng dần, phân trang bằng `turns_limit` (1–500, mặc định 100) và `turns_offset`. Mỗi lượt có dạng như [API lượt hỏi đáp](api-luot-hoi-dap.md).

## Sửa và xóa

`PATCH` chỉ đổi trường được gửi (giá trị `null` bị bỏ qua). Hội thoại không tồn tại hoặc thuộc người khác trả 404 `Không tìm thấy hội thoại.` cho cả đọc, sửa và xóa.
