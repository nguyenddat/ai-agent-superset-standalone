# API lưu từ điển mức bảng

**Trạng thái:** đã triển khai. **Endpoint:** `PUT /api/v1/tables/{table_id}/dictionary`.

## Mục đích

Tạo hoặc thay toàn bộ phần mô tả mức bảng: tên hiển thị, mô tả, ý nghĩa của một dòng, loại bảng, cách tổ chức chỉ số, vai trò cột, grain thời gian và ánh xạ tổng hợp chỉ số. Không động đến từ điển của từng cột.

## Request

| Trường | Bắt buộc | Ràng buộc |
| --- | --- | --- |
| `display_name` | Có | 1–255 ký tự sau khi bỏ khoảng trắng hai đầu. |
| `description`, `grain_description` | Không | Tối đa 2000 ký tự; chuỗi rỗng lưu thành null. |
| `table_kind` | Không | `base` hoặc `aggregate`. |
| `layout` | Không | `wide` (mặc định), `indicator_values`, `indicator_catalog`. |
| `indicator_catalog_table_id` | Không | ID bảng danh mục chỉ số; chỉ dùng với `indicator_values`. |
| `contains_pii` | Không | Mặc định `false`. |
| `column_roles` | Không | Tối đa 50 phần tử `{role, qualifier, column_id}`. |
| `time_grains` | Không | Tối đa 50 phần tử `{row_kind_value, label, time_grain}`. |
| `indicator_aggregations` | Không | Tối đa 20 phần tử `{source_code, aggregation}`. |

Trường không khai báo trong schema bị từ chối. Request là bản đầy đủ: trường hoặc danh sách bị bỏ trống được lưu là null hoặc rỗng, không giữ giá trị cũ.

## Luồng xử lý hiện tại

1. Đọc bảng theo `table_id`; không có thì trả 404. Route đòi `X-Service-Key` (xem [hành vi API](../../hanh-vi-api.md)), chưa phân quyền theo người dùng.
2. Kiểm tra `column_roles` theo `layout`:
   - `wide` cho phép `time`, `created_at`, `row_kind`.
   - `indicator_values` cho phép thêm `indicator_key` và `value`, bắt buộc có cả hai.
   - `indicator_catalog` cho phép thêm các vai trò `catalog_*`, bắt buộc có `catalog_key`, `catalog_code`, `catalog_name`.
   - `qualifier` chỉ dùng với `value` và phải là `number`, `boolean` hoặc `text`. Mỗi cặp `(role, qualifier)` xuất hiện một lần.
   - `column_id` phải là cột của chính bảng này; cột `indicator_key` không được đồng thời là cột `value`.
3. Kiểm tra `time_grains`: `time_grain` thuộc `instant`, `hour`, `day`, `week`, `month`, `quarter`, `year`. Có cột vai trò `row_kind` thì mỗi grain cần `row_kind_value` khác nhau; không có thì `row_kind_value` phải để trống và chỉ có một grain.
4. Kiểm tra `indicator_aggregations`: chỉ dùng khi `layout = indicator_catalog` và có vai trò `catalog_aggregation`; `source_code` không lặp; `aggregation` thuộc `SUM`, `AVG`, `MIN`, `MAX`, `COUNT`, `NONE`.
5. Kiểm tra `indicator_catalog_table_id`: khác bảng hiện tại, cùng kết nối database, và bảng đó đã được lưu với `layout = indicator_catalog`. Lưu dưới dạng ID từ điển của bảng danh mục.
6. Tạo bản ghi `table_dictionaries` nếu chưa có, ngược lại cập nhật. Nếu bảng đang là danh mục chỉ số và đổi sang layout khác, xóa liên kết `indicator_catalog_id` của các bảng đang trỏ tới nó.
7. Xóa toàn bộ vai trò, grain, ánh xạ tổng hợp cũ rồi tạo lại từ request.
8. Route commit một lần; lỗi kiểm tra trả 422 với thông báo chỉ rõ phần tử sai (ví dụ `column_roles[1].column_id không thuộc bảng này.`), lỗi khác rollback.
9. Trả về `TableDictionaryOut` như [API đọc](api-doc-tu-dien.md).

## Lưu ý thiết kế

Gán vai trò `row_kind` có thể đổi `semantic_role` mặc định của cột đó sang `row_kind` khi đọc. Danh sách mã chỉ số trong `indicator_aggregations` do người dùng nhập; đọc danh sách mã từ dữ liệu của bảng danh mục là phần **dự kiến**.
