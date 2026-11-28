# Glossary Management

**Trạng thái:** backend, migration và tab `Thuật ngữ` đã triển khai. API đòi `X-Service-Key` (xem [hành vi API](../../hanh-vi-api.md)), chưa phân quyền theo người dùng.

Module lưu thuật ngữ nghiệp vụ theo database connection, định nghĩa và từ đồng nghĩa theo revision, cùng liên kết tới bảng, cột và metric của connection đó. Bản nháp mới không thay bản đã duyệt đang được discovery trả về. Thu hồi tạo một revision `revoked` để chặn discovery; có thể soạn và duyệt lại sau đó.

Tên chuẩn của thuật ngữ là duy nhất trong một connection sau khi gộp khoảng trắng và `casefold`, và không đổi sau khi tạo. Thuật ngữ được gom theo [miền nghiệp vụ](../business_model/api-mien-nghiep-vu.md) của semantic model, không còn nhóm tự đặt; một thuật ngữ có thể thuộc nhiều miền hoặc chưa thuộc miền nào.

Xem [dữ liệu và quan hệ](du-lieu.md) và [API quản lý thuật ngữ](api-quan-ly.md).
