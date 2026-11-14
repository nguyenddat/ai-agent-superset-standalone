# Glossary Management

**Trạng thái:** backend, migration và tab `Thuật ngữ` đã triển khai. API chưa có xác thực/phân quyền.

Module lưu thuật ngữ nghiệp vụ theo database connection, định nghĩa và từ đồng nghĩa theo revision, cùng liên kết tới bảng, cột và metric của connection đó. Bản nháp mới không thay bản đã duyệt đang được discovery trả về. Thu hồi tạo một revision `revoked` để chặn discovery; có thể soạn và duyệt lại sau đó.

Tên chuẩn của thuật ngữ là duy nhất trong một connection sau khi gộp khoảng trắng và `casefold`, và không đổi sau khi tạo. `group_name` là nhãn nhóm tự do; chưa có bảng hoặc API quản lý nhóm.

Xem [dữ liệu và quan hệ](du-lieu.md) và [API quản lý thuật ngữ](api-quan-ly.md).
