# API thống kê từ điển của một kết nối

**Trạng thái:** đã triển khai. **Endpoint:** `GET /api/v1/database-connections/{connection_id}/dictionary-stats?limit=5`.

## Mục đích

Cung cấp số liệu cho tab `Tổng quan` của kết nối: mức độ mô tả của bảng và cột, bảng có nhiều cột nhất và bảng được tham chiếu nhiều nhất.

## Tham số

| Tham số | Ràng buộc |
| --- | --- |
| `limit` | Số bảng tối đa trong mỗi danh sách xếp hạng, 1–20, mặc định 5. Ngoài khoảng trả 422. |

## Luồng xử lý hiện tại

1. Dùng lại dữ liệu của [API tổng quan](api-tong-quan-ket-noi.md); kết nối không tồn tại trả 404. Route đòi `X-Service-Key` (xem [hành vi API](../../hanh-vi-api.md)), chưa phân quyền theo người dùng.
2. Đọc các cặp (bảng có cột tham chiếu, bảng được tham chiếu) từ `column_dictionaries.referenced_column_id` trong một truy vấn, chỉ giữ cặp mà cả hai bảng thuộc kết nối và khác nhau.
3. Xếp hạng theo giá trị giảm dần, rồi theo tên schema và tên bảng; bỏ bảng có giá trị 0.
4. Không ghi gì vào database.

## Kết quả

| Trường | Ý nghĩa |
| --- | --- |
| `table_count`, `described_table_count` | Tổng số bảng/view và số bảng đã có từ điển mức bảng. |
| `column_count`, `described_column_count` | Tổng số cột và số cột đã có từ điển mức cột. |
| `schemas[]` | `schema_id`, `schema_name`, `table_count`, `described_table_count` theo từng schema. |
| `most_columns[]` | `table_id`, `schema_name`, `table_name`, `display_name`, `is_saved`, `column_count`, `described_column_count`. |
| `most_referenced[]` | Như trên nhưng có `referencing_table_count`: số bảng khác có ít nhất một cột trỏ tới bảng này. |

## Giới hạn

Tham chiếu chỉ lấy từ khóa ngoại logic khai báo trong từ điển cột. Đồng bộ metadata chưa đọc khóa ngoại của database nguồn, nên khi chưa cột nào khai báo `referenced_column_id`, `most_referenced` rỗng.
