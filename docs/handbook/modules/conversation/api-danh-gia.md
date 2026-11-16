# API đánh giá lượt

**Trạng thái:** đã triển khai tại `/api/v1/conversations/{id}/turns/{turn_id}/feedback`.

| Method | Path | Hành vi |
| --- | --- | --- |
| PUT | `/{id}/turns/{turn_id}/feedback` | Ghi hoặc thay đánh giá `{user_id, rating, comment?}`; trả 200 với `rating`, `comment`, `created_at`, `updated_at`. |
| DELETE | `/{id}/turns/{turn_id}/feedback?user_id=...` | Xóa đánh giá; trả 204 kể cả khi chưa có đánh giá. |

`rating` chỉ nhận `up` hoặc `down`, `comment` tối đa 2000 ký tự (sai trả 422); `comment` rỗng sau khi bỏ khoảng trắng được lưu là `null`. Ghi lại thay toàn bộ `rating` và `comment` (không gửi `comment` thì xóa nhận xét cũ). Mỗi `(turn_id, user_id)` có tối đa một đánh giá; tranh chấp ghi đồng thời được xử lý bằng savepoint rồi cập nhật bản đã có.

Chỉ chủ hội thoại đánh giá được; `user_id` khác trả 404 `Không tìm thấy hội thoại.`
