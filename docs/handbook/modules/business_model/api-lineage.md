# API cạnh lineage

**Trạng thái:** đã triển khai. Các endpoint có tiền tố `/api/v1/business-model/connections/{connection_id}`:

| Phương thức và đường dẫn | Chức năng |
| --- | --- |
| `PUT /lineage-edges` | Tạo hoặc cập nhật bản ghi cạnh theo cặp bảng và `kind`. |
| `DELETE /lineage-edges/{edge_id}` | Xóa bản ghi cạnh/override trong kết nối, trả 204. |

Body ghi cạnh gồm `source_table_id`, `target_table_id` và `kind` (`flow` hoặc `relation`); tùy chọn `label` (tối đa 32 ký tự), `color` (`#RRGGBB` hoặc null), `is_hidden` (mặc định false), `is_manual` (mặc định true). Hai bảng phải khác nhau và thuộc kết nối trong URL, nếu không trả 422. Nếu một bảng chưa có từ điển mức bảng, service tạo bản ghi mặc định trước khi lưu cạnh. Bộ `(source, target, kind)` là duy nhất; ghi lại bộ đó cập nhật bản ghi cũ. Xóa cạnh không thuộc kết nối trả 404.

[API đọc mô hình](api-doc-mo-hinh.md) suy cạnh từ khai báo cột tham chiếu rồi ghép các bản ghi đã lưu: cạnh ẩn bị bỏ khỏi kết quả, thuộc tính nhãn/màu của override áp lên cạnh suy ra, cạnh thủ công được thêm vào. Xóa override của cạnh suy ra làm cạnh đó xuất hiện lại.
