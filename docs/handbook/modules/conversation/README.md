# Conversation

**Trạng thái:** model, migration, repository, service và API quản lý lịch sử trò chuyện **đã triển khai**. Route chat `POST /api/v1/text2sql/chat` và bản stream `POST /api/v1/text2sql/chat/stream` ghi mỗi lượt vào module này khi request có `user_id` (xem [ghi lượt từ pipeline](ghi-luot-tu-pipeline.md)). Giao diện là tab `Hỏi dữ liệu` của frontend (xem [handbook frontend](../../frontend/README.md#hỏi-dữ-liệu)).

Module lưu hội thoại hỏi đáp dữ liệu của một người dùng trên một database nguồn (`connection_id`), tương đương `AgentChatSession`/`AgentQuestion` của extension nhưng gắn với connection thay cho dashboard. Mỗi hội thoại gồm các lượt hỏi đáp đánh số tăng dần; mỗi lượt lưu câu hỏi, câu hỏi đã viết lại, câu trả lời, các bước xử lý, kết quả truy vấn đã che PII và đánh giá của người dùng.

## Mô hình dữ liệu

Ba bảng trong schema mặc định, migration ở `backend/migrations/versions/init_conversation_module/` (revision `a4c2e8f61b37` nối sau `7e4c1a9b5d32` tạo bảng; `c5e1d7a3b902` thêm cột làm rõ và tiếp tục lượt; `f4b8d2a6c913` sau `e8b2c6d4f170` thêm cột `views` lưu biểu đồ người dùng chọn cho từng kết quả). Chi tiết cột và ràng buộc ở [dữ liệu](du-lieu.md).

| Bảng | Vai trò |
| --- | --- |
| `conversations` | Hội thoại: connection, `user_id`, tiêu đề, ghim, lưu trữ, thời điểm có tin nhắn cuối. |
| `conversation_turns` | Một lượt hỏi đáp: thứ tự, câu hỏi, câu trả lời, trạng thái, luồng, bước, kết quả, câu hỏi làm rõ và lựa chọn, lỗi nội bộ, trạng thái tiếp tục (nội bộ). |
| `conversation_turn_feedback` | Đánh giá `up`/`down` và nhận xét của người dùng cho một lượt. |

Xóa connection xóa các hội thoại của nó; xóa hội thoại xóa lượt và đánh giá; xóa một lượt xóa đánh giá của lượt đó và đặt `retry_of` của lượt thử lại, `continued_from` của lượt tiếp tục về `NULL`.

## Quy tắc sở hữu

Mọi thao tác đều nhận `user_id`. Hội thoại của người khác được báo **không tìm thấy** (404), giống `require_own_session` của extension, để không tiết lộ hội thoại có tồn tại hay không. Lượt và đánh giá chỉ truy cập được qua hội thoại sở hữu.

`user_id` do client gửi lên và **chưa được xác thực** (giống `own_knowledge`). Đây là phân tách tiện dụng giữa người dùng, **không phải** cơ chế bảo mật: ai biết `user_id` và ID hội thoại đều đọc, sửa được. Khi có đăng nhập, `user_id` phải lấy từ phiên đã xác thực ở server.

## Giới hạn

- Dịch vụ không tự che PII; `results` lưu đúng dữ liệu route chat đã gửi cho client. Route chat hiện **không che PII** (presidio đã gỡ), nên dòng lưu là dữ liệu thô; xem [ghi lượt từ pipeline](ghi-luot-tu-pipeline.md#dữ-liệu-và-pii).
- Mỗi truy vấn trong `results` chỉ giữ tối đa `CONVERSATION_MAX_STORED_ROWS` dòng (mặc định 200); khi cắt, mục đó có `stored_truncated: true`.
- `error_message` và `continuation` là dữ liệu nội bộ; API không trả hai trường này (trả `error_code` và thông điệp chung `error`).
- `recent_history` cung cấp lịch sử gọn (câu hỏi và câu trả lời cuối cùng rút gọn 500 ký tự; lượt hỏi lại thì là câu hỏi lại) cho bước viết lại câu hỏi của pipeline chat; không bao giờ chứa dòng dữ liệu.
- API không có route tạo lượt; lượt chỉ do pipeline chat ghi qua service.
- Hai hàm chỉ đọc phục vụ câu hỏi gợi ý của text2sql: `answered_questions(connection_id, user_id, limit)` (câu hỏi của đúng người dùng đó trên connection, lượt `answered`, bỏ lượt có đánh giá `down`, mới nhất trước) và `metric_usage(connection_id, turns=500)` (đếm `results[].metric.name` của các lượt `answered` gần nhất trên connection, mọi người dùng, chỉ trả số đếm theo tên metric).

## Luồng

- [API hội thoại](api-hoi-thoai.md) — tạo, liệt kê, xem, sửa, xóa hội thoại (**đã triển khai**).
- [API lượt hỏi đáp](api-luot-hoi-dap.md) — liệt kê, xem, xóa lượt; lưu và bỏ lựa chọn biểu đồ của từng kết quả (**đã triển khai**).
- [API đánh giá lượt](api-danh-gia.md) — ghi và xóa đánh giá (**đã triển khai**).
- [Ghi lượt từ pipeline chat](ghi-luot-tu-pipeline.md) — service cho pipeline và cách pipeline chat ghi lượt (**đã triển khai**).
