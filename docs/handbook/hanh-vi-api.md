# Hành vi chung của API

**Trạng thái:** API FastAPI của `database_connection`, `data_dictionary`, `business_model` và `data_lineage` đã triển khai tại `/api/v1`; chưa có xác thực/phân quyền.

## Luồng xử lý

```text
Route → kiểm tra dữ liệu vào → service → repository → commit → response
```

Route sở hữu session của request qua `get_database()`. Service và repository không tự commit. Một thao tác ghi commit một lần sau khi mọi bước đã thành công; khi phát sinh exception, `get_database()` rollback và đóng session. Repository có thể flush để lấy ID hoặc phát hiện ràng buộc sớm. Không trả URI hoặc secret đã giải mã trong response.

## Lỗi

`backend.common.base_exceptions` định nghĩa lỗi gốc với `status`, `code` và thông điệp an toàn cho client. Module `database_connection` khai báo subclass trong `utils/exceptions.py`; lỗi từ driver hoặc SQLAlchemy được chuyển sang lỗi nghiệp vụ ở lớp hiểu được ý nghĩa của nó. Không đưa SQL, stack trace hoặc mật khẩu vào thông điệp lỗi. Mọi lỗi HTTP trả JSON dạng `{"detail":"..."}`; lỗi xác thực cấu trúc request trả thông điệp chung để không lộ URI.

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
