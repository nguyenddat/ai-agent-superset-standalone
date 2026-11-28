# API lưu từ điển mức cột

**Trạng thái:** đã triển khai. **Endpoint:** `PUT /api/v1/tables/{table_id}/dictionary/columns`.

## Mục đích

Lưu từ điển cho một hoặc nhiều cột của cùng một bảng trong một request. Chỉ các cột có trong request bị thay đổi; cột khác giữ nguyên. Từ điển cột lưu được cả khi bảng chưa có từ điển mức bảng.

## Request

Body là `{"columns": [...]}`, tối đa 1000 phần tử. Mỗi phần tử:

| Trường | Bắt buộc | Ràng buộc |
| --- | --- | --- |
| `column_id` | Có | Cột của bảng `table_id`, không lặp trong request. |
| `display_name` | Có | 1–255 ký tự. |
| `description`, `business_term` | Không | Tối đa 2000 ký tự. |
| `semantic_role` | Không | `key`, `measure`, `dimension`, `label`, `time`, `row_kind`, `attribute`; null để dùng mặc định. |
| `temporal_kind` | Không | `date`, `timestamp`. |
| `unit`, `format` | Không | Tối đa 128 ký tự. |
| `is_primary_key` | Không | Null nghĩa là theo khóa chính ở nguồn và quy tắc theo tên. |
| `is_unique`, `contains_pii` | Không | Mặc định `false`. |
| `referenced_column_id` | Không | Cột được tham chiếu (khóa ngoại logic). |
| `aggregations` | Không | `SUM`, `AVG`, `MIN`, `MAX`, `COUNT`, `COUNT_DISTINCT`; giá trị lặp bị gộp. |
| `synonyms` | Không | Tối đa 20 từ sau khi gộp, mỗi từ tối đa 100 ký tự. |

Mỗi phần tử là bản đầy đủ của cột đó: trường bỏ trống được lưu là null, `false` hoặc rỗng.

## Luồng xử lý hiện tại

1. Đọc bảng theo `table_id`; không có thì trả 404. Route đòi `X-Service-Key` (xem [hành vi API](../../hanh-vi-api.md)), chưa phân quyền theo người dùng.
2. Đọc cột của bảng, vai trò `row_kind` đã lưu ở mức bảng và từ điển đã có của các cột.
3. Đọc mọi `referenced_column_id` trong request bằng một truy vấn; mỗi cột được tham chiếu phải tồn tại và thuộc cùng kết nối database (có thể khác schema).
4. Kiểm tra từng phần tử trước khi ghi:
   - `column_id` thuộc bảng và không lặp; `referenced_column_id` khác chính cột đó.
   - Tính `semantic_role` hiệu lực (giá trị gửi lên, hoặc mặc định như [API đọc](api-doc-tu-dien.md#giá-trị-mặc-định)). `aggregations` chỉ được có khi vai trò hiệu lực là `measure`.
   - Synonym bỏ khoảng trắng hai đầu, bỏ chuỗi rỗng, gộp trùng không phân biệt hoa thường và giữ cách viết đầu tiên.
5. Chỉ khi mọi phần tử hợp lệ mới ghi: tạo `column_dictionaries` nếu chưa có, ngược lại cập nhật và xóa aggregation, synonym cũ; sau đó tạo aggregation, synonym mới.
6. Route commit một lần; lỗi kiểm tra trả 422 với vị trí phần tử (ví dụ `columns[0].aggregations chỉ dùng cho cột có vai trò measure.`), lỗi khác rollback.
7. Trả về `TableDictionaryOut` của cả bảng như [API đọc](api-doc-tu-dien.md).

## Lưu ý thiết kế

Trường `columns` bắt buộc; danh sách rỗng hợp lệ và không ghi gì. Gợi ý mô tả bằng AI xem [tự động điền](api-tu-dong-dien.md); phân tích dữ liệu nguồn để đề xuất grain hoặc vai trò, và đánh dấu PII tự động là phần **dự kiến**.
