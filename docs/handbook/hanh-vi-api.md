# Hành vi chung của API

**Trạng thái:** quy ước cho API sẽ triển khai; repository hiện chưa có web framework hoặc route hoạt động.

## Luồng xử lý

```text
Route → kiểm tra quyền và dữ liệu vào → service → repository → commit → formatter → response
```

Route sở hữu session của request qua `get_database()`. Service và repository không tự commit. Một thao tác ghi commit một lần sau khi mọi bước đã thành công; khi phát sinh exception, `get_database()` rollback và đóng session. Repository có thể flush để lấy ID hoặc phát hiện ràng buộc sớm. Không trả URI hoặc secret đã giải mã trong response.

## Lỗi

`backend.common.base_exceptions` định nghĩa lỗi gốc với `status`, `code` và thông điệp an toàn cho client. Mỗi module khai báo subclass cụ thể trong `exceptions.py`; lỗi từ driver hoặc SQLAlchemy được chuyển sang lỗi nghiệp vụ ở lớp hiểu được ý nghĩa của nó. Không đưa SQL, stack trace hoặc mật khẩu vào thông điệp lỗi.

| Nhóm lỗi | HTTP status |
| --- | ---: |
| Dữ liệu không hợp lệ | 400 |
| Chưa xác thực | 401 |
| Không có quyền | 403 |
| Không tìm thấy | 404 |
| Xung đột trạng thái hoặc tên | 409 |
| Quá nhiều yêu cầu | 429 |
| Dịch vụ phụ thuộc không sẵn sàng | 503 |

HTTP framework, đường dẫn endpoint, schema JSON và cơ chế xác thực chưa được chọn trong code. Tài liệu luồng API từng module ghi rõ đầu vào, kiểm tra, thao tác dữ liệu, lỗi, đầu ra và trạng thái triển khai; không coi tên đường dẫn dự kiến là hợp đồng đã phát hành.

## Định dạng response

Datetime xuất ISO 8601 UTC với sáu chữ số phần giây và `Z`; date xuất `YYYY-MM-DD`. UUID và Decimal xuất chuỗi; số nguyên, chuỗi và boolean giữ kiểu JSON tương ứng. Datetime thiếu timezone bị từ chối tại biên chuyển đổi để tránh hiểu sai thời điểm.
