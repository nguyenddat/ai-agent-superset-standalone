# Expert Rule Management

**Trạng thái:** backend, migration và tab `Quy tắc` đã triển khai. API đòi `X-Service-Key` (xem [hành vi API](../../hanh-vi-api.md)), chưa phân quyền theo người dùng.

Module lưu quy tắc chuyên gia theo một bảng metadata của database connection. Rule có tên ổn định và thuộc một hoặc nhiều [miền nghiệp vụ](../business_model/api-mien-nghiep-vu.md) của semantic model (có thể chưa thuộc miền nào); mỗi revision lưu mô tả, điều kiện có cấu trúc, ngoại lệ, ví dụ, liên kết tới glossary và metric. Bản nháp mới không thay bản đã duyệt đang được discovery trả về. Thu hồi tạo revision `revoked` và dừng công bố rule.

Một rule cần ít nhất một glossary term đã duyệt có liên kết sống tới cùng bảng. Metric là liên kết tùy chọn, nhưng nếu có phải đang hoạt động trên bảng đó. Rule ghim revision glossary và dấu vân tay metric tại lúc soạn; thay đổi sau đó khiến rule không xuất hiện ở discovery cho tới khi cập nhật và duyệt lại. Điều kiện tham chiếu cột bằng UUID, không nhận câu SQL tự do và API không thực thi truy vấn.

Xem [dữ liệu và quan hệ](du-lieu.md) và [API quản lý rule](api-quan-ly.md).
