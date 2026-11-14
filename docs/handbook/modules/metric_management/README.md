# Metric Management

**Trạng thái:** migration, API CRUD metric và đồng bộ một chiều Superset đã triển khai ở backend. Giao diện là tab `Metric` của trang chi tiết kết nối (xem [frontend](../../frontend/README.md#metric)). Chưa có API chạy truy vấn metric.

Metric tự tạo dùng tên và biểu thức SQL tổng hợp theo một bảng metadata của standalone, cùng các trường nhãn, mô tả, định dạng, tiền tệ và cảnh báo tương thích khái niệm saved metric của Superset. API chỉ lưu biểu thức, chưa thực thi hoặc chứng minh tính hợp lệ của SQL. Metric Superset được đọc từ REST API, gắn với ID metric/dataset/database/user nguồn và chỉ sửa được tại Superset. Không đồng bộ ngược.

Database của Superset được nhập như metadata, sau đó có thể liên kết với một database connection đã đăng ký trong standalone. API Superset không cung cấp credential kết nối để tái sử dụng an toàn; liên kết này dùng connection của standalone để đối chiếu bảng vật lý. Dataset ảo vẫn giữ thông tin SQL và không tự gắn vào một bảng vật lý. User Superset là bản sao danh tính để tham chiếu, không phải tài khoản đăng nhập standalone.

Tài liệu: [dữ liệu và migration](du-lieu.md), [API quản lý metric](api-quan-ly.md), [API đồng bộ Superset](api-dong-bo-superset.md).
