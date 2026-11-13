# Module `data_dictionary`

Module sở hữu từ điển dữ liệu: phần mô tả nghiệp vụ của bảng và cột trong database nguồn, phục vụ AI agent và người dùng hiểu dữ liệu. Thiết kế tham khảo module `data_dictionary` của Semantic Layer trong `ai-agent-superset-extension`, nhưng gắn với bảng và cột đã đồng bộ của module [`database_connection`](../database_connection/README.md) thay cho khái niệm dataset của Superset.

**Đã triển khai:**

- Model và revision Alembic cho từ điển mức bảng (`table_dictionaries`, `table_column_roles`, `table_time_grains`, `indicator_aggregations`) và mức cột (`column_dictionaries`, `column_aggregations`, `column_synonyms`).
- Repository và `DataDictionaryService` đọc, lưu từ điển cùng giá trị mặc định.
- `DataDictionaryAutofillService` tự động điền bằng mô hình ngôn ngữ, stream kết quả qua Server-Sent Events.
- FastAPI route với tiền tố `/api/v1`.

**Dự kiến:** quan hệ đã kiểm tra dữ liệu giữa các bảng, phân tích dữ liệu nguồn để gợi ý grain và vai trò, đọc danh sách mã chỉ số từ bảng danh mục, nhãn PII cho catalog của AI agent và giao diện.

Bản ghi từ điển chỉ được tạo khi người dùng lưu hoặc chạy tự động điền. Bảng hoặc cột chưa có bản ghi được API trả về giá trị mặc định suy ra từ metadata.

## Cấu trúc code

- `services/semantics.py`: hằng số giá trị hợp lệ và quy tắc suy mặc định (`temporal_kind`, `semantic_role`, nhận diện cột khóa theo tên).
- `services/dictionary_service.py`: kiểm tra và lưu từ điển; đọc bảng, cột qua repository của `database_connection`.
- `services/autofill_service.py`: chia lô, quy tắc chỉ điền chỗ trống, sinh sự kiện tiến độ.
- `services/dictionary_suggester.py`: schema structured output và lời gọi mô hình; dùng `backend/agent_package` cho chat model và prompt.
- Service không commit; route commit sau mỗi thao tác lưu, hoặc sau từng sự kiện khi tự động điền.

## Tài liệu module

- [Mô hình dữ liệu](du-lieu.md)
- [Đọc từ điển của bảng](api-doc-tu-dien.md)
- [Lưu từ điển mức bảng](api-luu-tu-dien-bang.md)
- [Lưu từ điển mức cột](api-luu-tu-dien-cot.md)
- [Tự động điền bằng AI](api-tu-dong-dien.md)

Luồng xử lý API áp dụng [hành vi chung](../../hanh-vi-api.md).
