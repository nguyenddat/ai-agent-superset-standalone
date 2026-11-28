# API tự động điền từ điển bằng AI

**Trạng thái:** đã triển khai. **Endpoint:** `POST /api/v1/tables/{table_id}/dictionary/autofill`, trả về luồng Server-Sent Events (`text/event-stream`).

## Mục đích

Dùng mô hình ngôn ngữ đề xuất tên hiển thị, mô tả, thuật ngữ nghiệp vụ, đơn vị của cột và tên hiển thị, mô tả, ý nghĩa một dòng, cột thời điểm tạo của bảng. Gợi ý được lưu ngay theo từng lô cột và đẩy về trình duyệt để giao diện điền trực tiếp khi mô hình trả lời. Tham khảo AI AutoFill của Semantic Layer trong `ai-agent-superset-extension`.

## Cấu hình

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | trống | Bắt buộc để dùng tính năng; thiếu thì API trả 503. |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Endpoint tương thích OpenAI. |
| `OPENROUTER_MODEL` | `openai/gpt-6-luna` | Mô hình dùng để gợi ý. |

`backend/agent_package/get_chat_models.py` tạo `ChatOpenAI` (nhiệt độ 0, timeout 60 giây, thử lại 2 lần); prompt nằm trong `backend/agent_package/prompts/`. Không ghi API key vào code, log hay tài liệu.

## Luồng xử lý hiện tại

1. **Trước khi stream** (lỗi trả JSON thông thường): đọc bảng (404 nếu không có), kiểm tra bảng có cột (422) và không quá 300 cột (422), kiểm tra đã cấu hình API key (503), và bảng không đang được tự động điền ở request khác (409). Sau đó kết thúc transaction đọc để không giữ kết nối trong lúc chờ mô hình. Route đòi `X-Service-Key` (xem [hành vi API](../../hanh-vi-api.md)), chưa phân quyền theo người dùng.
2. Chia cột thành lô 8 cột, gửi tối đa 4 lô đồng thời. Mỗi lô gồm schema, tên bảng, loại bảng, mô tả bảng và tên, kiểu dữ liệu, nullable, khóa chính, comment của cột.
3. Lô nào xong trước xử lý trước: bỏ gợi ý cho tên cột không thuộc lô, gợi ý trùng hoặc `display_name` rỗng; ghi gợi ý hợp lệ; route commit rồi gửi sự kiện `columns`. Lô lỗi được tính vào `failed_columns` và bỏ qua, trừ lỗi API key bị từ chối (401/403) hoặc hết hạn mức (402) thì dừng cả luồng.
4. Gợi ý mức bảng dùng thêm tên hiển thị và mô tả cột vừa được gợi ý; ghi rồi gửi sự kiện `table`. Lỗi ở bước này không làm mất các lô cột đã lưu.
5. Gửi `done`. Nếu không có cột nào và cả bảng đều không nhận được gợi ý thì gửi `error` thay cho `table` và `done`.

## Quy tắc ghi

Tự động điền chỉ điền chỗ trống, không ghi đè nội dung người dùng đã nhập:

- `display_name` của bảng hoặc cột chỉ được thay khi vẫn bằng tên vật lý.
- `description`, `business_term`, `unit`, `grain_description` chỉ được điền khi đang trống.
- Cột hoặc bảng chưa có bản ghi từ điển thì được tạo bản ghi. Comment ở nguồn được giữ làm mô tả nếu có. Cột mới giữ `temporal_kind` suy từ kiểu dữ liệu và để `semantic_role` null để vẫn dùng [quy tắc mặc định](api-doc-tu-dien.md#giá-trị-mặc-định).
- Vai trò `created_at` chỉ được gán khi bảng chưa có vai trò này, tên cột gợi ý khớp một cột của bảng và cột có kiểu ngày giờ.
- Độ dài được cắt theo giới hạn của từng trường. Vai trò cột, phép tổng hợp, synonym, khóa và PII không được tự động điền.

## Sự kiện

Mỗi sự kiện có dạng `event: <tên>` và `data: <JSON>`:

| Sự kiện | Dữ liệu |
| --- | --- |
| `status` | `processed`, `total`, `message` (thông điệp tiến độ tiếng Việt). |
| `columns` | `columns`: danh sách `ColumnDictionaryOut` của các cột vừa được điền; `processed`, `total`. |
| `table` | `TableDictionaryOut` đầy đủ sau khi điền mức bảng, như [API đọc](api-doc-tu-dien.md). |
| `done` | `processed`, `total`, `failed_columns`, `table_filled`. |
| `error` | `code`, `message`. Các lô đã gửi `columns` trước đó vẫn được lưu. |

Trình duyệt gọi bằng `fetch` với phương thức POST rồi đọc `response.body` theo từng sự kiện; `EventSource` không dùng được vì chỉ hỗ trợ GET.

## Lưu ý thiết kế

`DataDictionaryAutofillService` (thứ tự lô, quy tắc ghi, sự kiện) tách khỏi `LlmDictionarySuggester` (prompt, structured output, gọi mô hình) để test dùng suggester giả, không cần mạng hay API key. Khóa "đang tự động điền" giữ trong bộ nhớ tiến trình nên chỉ đúng khi backend chạy một tiến trình; chạy nhiều worker cần khóa dùng chung (ví dụ advisory lock của PostgreSQL). Người dùng sửa từ điển trong lúc tự động điền vẫn được giữ vì mỗi lô đọc lại bản ghi ngay trước khi ghi. Gợi ý từ dữ liệu mẫu của nguồn, gợi ý vai trò và đánh dấu PII là phần **dự kiến**.
