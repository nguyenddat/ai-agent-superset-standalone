# Hành vi chung của API

**Trạng thái:** API FastAPI của `database_connection`, `data_dictionary`, `business_model`, `data_lineage`, `metric_management`, `glossary_management`, `expert_rule_management`, `own_knowledge`, `text2sql` (ingestion, retrieve, chat) và `conversation` đã triển khai tại `/api/v1`. Các module trước chưa có xác thực/phân quyền; `own_knowledge` dùng khóa dịch vụ Agent và admin riêng. `conversation` phân tách dữ liệu theo `user_id` do client gửi (chưa xác thực) và trả 404 cho hội thoại của người khác; xem [module conversation](modules/conversation/README.md).

## Luồng xử lý

```text
Route → kiểm tra dữ liệu vào → service → repository → commit → response
```

Route sở hữu session của request qua `get_database()`. Service và repository không tự commit. Một thao tác ghi commit một lần sau khi mọi bước đã thành công; khi phát sinh exception, `get_database()` rollback và đóng session. Repository có thể flush để lấy ID hoặc phát hiện ràng buộc sớm. Không trả URI hoặc secret đã giải mã trong response.

Ngoại lệ: route streaming `POST /api/v1/text2sql/chat` trả `text/event-stream` và không dùng `get_database()` vì vòng đời dependency không khớp với stream. Route kiểm tra đầu vào, connection và hội thoại (khi có `user_id`) bằng một session ngắn trước khi stream; generator tự mở session và client rồi đóng trong `finally` (kể cả khi client ngắt kết nối), chỉ commit dataset sau khi truy vấn chạy thành công, và ghi lượt hội thoại bằng một session riêng (commit khi mở và khi kết thúc lượt; ngắt kết nối thì lượt được đóng với `error_code=client_disconnected`). Xem [luồng chat](modules/text2sql/chat-flow.md).

## Lỗi

`backend.common.base_exceptions` định nghĩa lỗi gốc với `status`, `code` và thông điệp an toàn cho client. Module `database_connection` khai báo subclass trong `utils/exceptions.py`; lỗi từ driver hoặc SQLAlchemy được chuyển sang lỗi nghiệp vụ ở lớp hiểu được ý nghĩa của nó. Không đưa SQL, stack trace hoặc mật khẩu vào thông điệp lỗi. Mọi lỗi HTTP trả JSON dạng `{"detail":"..."}`; lỗi xác thực cấu trúc request trả thông điệp chung để không lộ URI. Với route streaming, lỗi trước khi stream bắt đầu trả HTTP lỗi như trên; lỗi sau đó được gửi thành event `error` (`{code, message}`) rồi kết thúc stream.

| Nhóm lỗi | HTTP status |
| --- | ---: |
| Dữ liệu kết nối hoặc request không hợp lệ | 422 |
| Chưa xác thực | 401 |
| Không có quyền | 403 |
| Không tìm thấy | 404 |
| Xung đột trạng thái hoặc tên | 409 |
| Quá nhiều yêu cầu | 429 |
| Dịch vụ phụ thuộc không sẵn sàng | 503 |

FastAPI cung cấp route và schema JSON. CORS cho phép các origin trong `FRONTEND_ORIGIN`, phân tách bằng dấu phẩy; mặc định là `http://localhost:3000,http://127.0.0.1:3000`. CORS không thay thế xác thực. Backend hiện chưa kiểm tra danh tính và quyền của người gọi, nên chỉ chạy trên môi trường phát triển tin cậy cho đến khi bổ sung chính sách truy cập.

## Định dạng response

API hiện dùng Pydantic để xuất datetime ISO 8601 và UUID dạng chuỗi. Formatter chung trong `backend.common.utils.type_formatters` quy định UTC với sáu chữ số phần giây và `Z`; route hiện chưa dùng formatter này. Số nguyên, chuỗi và boolean giữ kiểu JSON tương ứng.
