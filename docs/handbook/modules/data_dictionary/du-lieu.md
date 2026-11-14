# Mô hình dữ liệu của `data_dictionary`

**Trạng thái:** đã triển khai model và migration cho từ điển mức bảng và mức cột, gồm khai báo cột được tham chiếu. Quan hệ giữa các bảng được kiểm tra bằng dữ liệu để phục vụ AI agent là **dự kiến**.

```text
database_tables (1) ── (0..1) table_dictionaries
                                 ├── (n) table_column_roles ──→ database_columns
                                 ├── (n) table_time_grains
                                 └── (n) indicator_aggregations

database_columns (1) ── (0..1) column_dictionaries
                                 ├── (n) column_aggregations
                                 └── (n) column_synonyms
```

Mọi bảng của module kế thừa `AuditedModel`: ID UUID v7, `created_at`, `updated_at`, `created_by_id`, `updated_by_id`. Mọi tham chiếu đến bảng hoặc cột nguồn là khóa ngoại, không lưu tên dạng chuỗi.

## `table_dictionaries`

| Trường | Ý nghĩa |
| --- | --- |
| `table_id` | FK đến `database_tables`, duy nhất, `ON DELETE CASCADE`. |
| `layer_id` | FK nullable đến `data_layers`, `ON DELETE SET NULL`; chuẩn bị cho phân tầng trong `business_model`. API từ điển hiện chưa đọc hoặc sửa trường này. |
| `display_name`, `description` | Tên và mô tả nghiệp vụ. |
| `grain_description` | Một dòng của bảng đại diện cho cái gì, viết bằng chữ. |
| `table_kind` | `base` (bảng gốc), `aggregate` (bảng tổng hợp) hoặc null. |
| `layout` | `wide` (mặc định, mỗi chỉ số một cột), `indicator_values` (mỗi dòng một chỉ số và giá trị), `indicator_catalog` (danh mục giải thích các chỉ số). |
| `indicator_catalog_id` | Với `indicator_values`: FK đến từ điển của bảng danh mục chỉ số, `ON DELETE SET NULL`. |
| `contains_pii` | Bảng có dữ liệu cá nhân cần xử lý như dữ liệu nhạy cảm. |

## `table_column_roles`

Gán vai trò đặc biệt cho cột của bảng. `column_id` là FK đến `database_columns` `ON DELETE CASCADE`: cột bị xóa khi đồng bộ thì vai trò mất theo. Cặp `(table_dictionary_id, role, qualifier)` duy nhất với `NULLS NOT DISTINCT`.

| Áp dụng cho | `role` | `qualifier` |
| --- | --- | --- |
| Mọi bảng | `time` (cột thời gian chính), `created_at` (thời điểm tạo bản ghi) | null |
| Bảng trộn nhiều grain | `row_kind` (cột phân biệt loại dòng) | null |
| `indicator_values` | `indicator_key` (cột cho biết dòng là chỉ số nào) | null |
| `indicator_values` | `value` (cột chứa giá trị) | Kiểu giá trị: `number`, `boolean`, `text` |
| `indicator_catalog` | `catalog_key`, `catalog_code`, `catalog_name`, `catalog_unit`, `catalog_value_kind`, `catalog_aggregation` | null |

## `table_time_grains`

Độ chi tiết thời gian của bảng: `time_grain` là `instant`, `hour`, `day`, `week`, `month`, `quarter` hoặc `year`; `label` là tên hiển thị. Bảng thông thường có một dòng với `row_kind_value` null. Bảng trộn nhiều grain có một dòng cho mỗi giá trị của cột vai trò `row_kind`. Cặp `(table_dictionary_id, row_kind_value)` duy nhất với `NULLS NOT DISTINCT`.

`grain_description` và `time_grain` là hai khái niệm khác nhau: thứ nhất là thực thể của một dòng ("một đơn hàng"), thứ hai là độ chi tiết thời gian ("theo ngày").

## `indicator_aggregations`

Với `indicator_catalog`: ánh xạ mã cách tổng hợp có trong dữ liệu nguồn (`source_code`) sang phép SQL (`aggregation`: `SUM`, `AVG`, `MIN`, `MAX`, `COUNT`, `NONE`). Cặp `(table_dictionary_id, source_code)` duy nhất.

## `column_dictionaries`

Từ điển của một cột, độc lập với từ điển của bảng chứa nó: cột có thể được mô tả khi bảng chưa có bản ghi từ điển. Lấy từ điển cột theo bảng bằng cách nối qua `database_columns.table_id`.

| Trường | Ý nghĩa |
| --- | --- |
| `column_id` | FK đến `database_columns`, duy nhất, `ON DELETE CASCADE`. |
| `display_name`, `description` | Tên và mô tả nghiệp vụ. |
| `business_term` | Thuật ngữ nghiệp vụ mà cột biểu diễn. |
| `semantic_role` | Cách cột được dùng khi phân tích: `key`, `measure`, `dimension`, `label`, `time`, `row_kind`, `attribute`. Null nghĩa là chưa khai báo; service suy mặc định từ kiểu dữ liệu và khóa chính. |
| `temporal_kind` | Với cột thời gian: `date` hoặc `timestamp`. Lọc theo ngày trên cột `timestamp` phủ cả ngày. |
| `unit`, `format` | Đơn vị (VND, %, kg) và định dạng hiển thị. |
| `is_primary_key` | Khóa chính logic do người dùng khai báo. Null nghĩa là lấy theo `database_columns.is_primary_key` đọc từ nguồn; dùng cho view hoặc bảng kho dữ liệu không khai báo khóa. |
| `is_unique` | Giá trị của cột là duy nhất theo nghiệp vụ, kể cả khi database không khai báo ràng buộc. |
| `referenced_column_id` | Cột mà cột này tham chiếu (khóa ngoại logic), FK đến `database_columns` `ON DELETE SET NULL`. Khác null nghĩa là cột là khóa ngoại. |
| `contains_pii` | Cột có dữ liệu cá nhân. |

Thông tin vật lý (tên, kiểu dữ liệu, nullable, giá trị mặc định) đọc từ `database_columns`, không lưu lại. Khai báo khóa ngoại ở đây là thông tin mô tả; quan hệ đã kiểm tra dữ liệu để AI agent nối bảng là phần **dự kiến** riêng.

`semantic_role = 'time'` đánh dấu mọi cột thời gian; vai trò `time` trong `table_column_roles` chỉ ra cột thời gian chính của bảng.

## `column_aggregations` và `column_synonyms`

- `column_aggregations.aggregation`: phép tổng hợp có nghĩa trên cột `measure`: `SUM`, `AVG`, `MIN`, `MAX`, `COUNT`, `COUNT_DISTINCT`. Cặp `(column_dictionary_id, aggregation)` duy nhất.
- `column_synonyms.synonym`: từ người dùng dùng để gọi cột, tối đa 100 ký tự. Cặp `(column_dictionary_id, synonym)` duy nhất.

Hai danh sách tách thành bảng con thay vì JSON để kiểm tra trùng ở database và tìm cột theo từ đồng nghĩa bằng SQL.

## Kiểm tra ở service

Database không tự đảm bảo các quy tắc sau; service phải kiểm tra khi lưu:

1. Cột trong `table_column_roles` thuộc đúng bảng của từ điển.
2. Vai trò khớp `layout`, ví dụ bảng `wide` không có vai trò `catalog_*`; `indicator_catalog_id` chỉ dùng với `indicator_values` và trỏ tới từ điển có `layout = indicator_catalog`.
3. Bảng có vai trò `row_kind` thì mỗi dòng `table_time_grains` có `row_kind_value`.
4. `column_aggregations` chỉ có trên cột có `semantic_role = 'measure'`; `temporal_kind` chỉ có trên cột thời gian; `referenced_column_id` không trỏ vào chính cột đó.
5. Giá trị liệt kê (`table_kind`, `layout`, `role`, `qualifier`, `time_grain`, `aggregation`, `semantic_role`, `temporal_kind`) hợp lệ. Không dùng CHECK constraint để thêm giá trị mới không cần migration.

## Khác biệt với extension

| Extension (`text_to_bi_*`) | Standalone |
| --- | --- |
| `dataset_dictionary.id` dùng chung ID với dataset Superset | `table_dictionaries.table_id` tham chiếu `database_tables.id` |
| `dataset_name` | Bỏ; đọc từ `database_tables.name` |
| `dataset_type` | `table_kind` |
| `grain` (chữ) và `dataset_grain.grain` (giờ/ngày) cùng tên | `grain_description` và `table_time_grains.time_grain` |
| `create_column`, `time_column`, `row_kind_column` lưu tên cột | Vai trò `created_at`, `time`, `row_kind` trong `table_column_roles` |
| `indicator_model` là JSON chứa tên cột | `layout`, các vai trò `indicator_*`/`value`/`catalog_*`, `indicator_aggregations`, `indicator_catalog_id` |
| `layer_id` tham chiếu `data_layer` | Chưa có; quyết định khi làm phân lớp dữ liệu |
| `column_dictionary.column_name`, `data_type` | Đọc từ `database_columns` |
| `is_pk` do người dùng khai báo, khởi tạo `false` | `is_primary_key` nullable; null lấy khóa chính đọc từ nguồn |
| `nullable`, `default` do người dùng sửa | Bỏ; đọc từ `database_columns` |
| `is_fk` + `referenced_column` (ID từ điển cột) | `referenced_column_id` tham chiếu `database_columns`; khác null là khóa ngoại |
| `column_dictionary.dataset_id` | Bỏ; nối qua `database_columns.table_id` |
| `aggregations`, `synonyms` là JSON dạng text | Bảng con `column_aggregations`, `column_synonyms` |

## Quan hệ với đồng bộ metadata

Đồng bộ metadata xóa bảng và cột không còn ở nguồn. Bảng bị xóa thì từ điển và mọi bản ghi con bị xóa theo; cột bị xóa thì từ điển của cột và các vai trò gán cho cột đó bị xóa, còn `referenced_column_id` trỏ vào cột đó về null. Đồng bộ đối chiếu theo tên, nên bảng hoặc cột bị đổi tên ở nguồn được coi là mới và mất phần mô tả cũ.

Migration nằm trong `backend/migrations/versions/init_data_dictionary_module/`: `0a2af1e246a1` tạo từ điển mức bảng, nối sau revision cuối của `init_database_module`; `1ee3a3e45c38` tạo từ điển mức cột.
