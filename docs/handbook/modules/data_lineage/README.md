# Module `data_lineage`

**Trạng thái:** backend, migration, API và giao diện đã triển khai. Giao diện là tab `Dòng dữ liệu` của trang chi tiết kết nối (xem [Frontend](../../frontend/README.md#dòng-dữ-liệu)).

Module ghi một phép biến đổi từ nhiều bảng nguồn vào một bảng đích, lưu SQL gốc (nếu có) và các phụ thuộc cột đã được người dùng xác nhận. Đồ thị data flow được suy từ bảng nguồn của phép biến đổi. Quan hệ khóa ngoại trong Data Dictionary chỉ là `relation`, không tự trở thành data flow khi đổi thứ tự tầng dữ liệu.

Module không thực thi SQL đã nhập. API xem trước phân tích cú pháp PostgreSQL cho một câu `SELECT` có bảng trực tiếp trong `FROM`/`JOIN`; phần không xác định chắc được đưa vào `warnings` và người dùng có thể khai báo tay. Với view/materialized view, API đọc SQL định nghĩa bằng role của kết nối nguồn. Không tự đọc SQL của ETL/job bên ngoài.

Nguồn và đích hiện phải thuộc cùng một kết nối và đang nằm trong phạm vi metadata của kết nối. API chưa có xác thực người gọi; chỉ nên dùng trong môi trường phát triển tin cậy cho đến khi có chính sách truy cập.

## Tài liệu

- [Dữ liệu và migration](du-lieu.md)
- [Xem trước SQL và đọc view](api-xem-truoc.md)
- [Quản lý phép biến đổi](api-quan-ly.md)
- [Đọc đồ thị](api-do-thi.md)
