# Phạm vi metadata của kết nối

**Trạng thái:** đã triển khai. Cấu hình khi `POST /api/v1/database-connections`, sửa bằng `PATCH /api/v1/database-connections/{id}` và đọc lại trong response kết nối.

Bốn trường là `schema_includes`, `schema_excludes`, `table_includes`, `table_excludes`; mỗi trường là danh sách tối đa 100 mẫu tên, mỗi mẫu dài tối đa 255 ký tự. Mặc định là `[]`. Mẫu phân biệt chữ hoa/thường, hỗ trợ `*` và `?`; tên bảng có thể là `orders*` hoặc kèm schema như `public.orders*`. Mẫu trong danh sách include rỗng nghĩa là lấy tất cả; exclude luôn có quyền ưu tiên. Schema hệ thống `information_schema` và `pg_*` vẫn bị bộ quét bỏ qua.

Ví dụ:

```json
{
  "schema_includes": ["public", "analytics_*"],
  "schema_excludes": ["analytics_tmp"],
  "table_includes": ["fact_*", "public.orders"],
  "table_excludes": ["tmp_*", "public.fact_test"]
}
```

Khi đồng bộ, service chỉ cập nhật schema/bảng được chọn và các cột của chúng. Metadata đã lưu nhưng bị loại bởi bộ lọc vẫn ở database ứng dụng, không bị xóa cùng từ điển hoặc mô hình nghiệp vụ. Các API liệt kê schema/bảng, tổng quan từ điển và mô hình nghiệp vụ chỉ hiện phần đang được chọn. API đọc trực tiếp theo ID vẫn đọc được bản ghi cũ; bộ lọc là phạm vi hiển thị và đồng bộ, không phải phân quyền. Khi mở lại phạm vi, bản ghi cũ xuất hiện với cùng ID; cần đồng bộ lại để làm mới hoặc xóa mục đã biến mất khỏi nguồn. Bảng được chọn nhưng thật sự biến mất khỏi nguồn vẫn theo chính sách xóa hiện tại.

Bộ quét hiện vẫn đọc snapshot đầy đủ từ PostgreSQL trước khi áp bộ lọc; tính năng này giảm lượng metadata hiển thị và lưu mới, chưa giảm thời gian quét nguồn. Đổi phạm vi không tự chạy đồng bộ; giao diện cần cho người dùng chạy lại `POST /sync` sau khi lưu cấu hình. Trong frontend, phạm vi được nhập ở bước 2 của form kết nối và toast sau khi lưu có nút `Đồng bộ ngay` (xem [Frontend](../../frontend/README.md)).
