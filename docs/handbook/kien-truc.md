# Kiến trúc ứng dụng

## Ranh giới hệ thống

```text
frontend/ → backend/modules/ → metadata database của ứng dụng
                         └──→ database nguồn đã đăng ký
```

Ứng dụng standalone không cần chạy Superset để lưu kết nối hay metadata. `DATABASE_URL` cấu hình metadata database của chính ứng dụng. URI của database nguồn nằm trong bản ghi `database_connections` và chỉ được dùng sau khi giải mã ở lớp nghiệp vụ tương ứng. Bốn bảng metadata nguồn là bản sao thông tin schema, bảng và cột; migration không tạo bảng trong database nguồn.

## Các lớp backend

| Lớp | Trách nhiệm |
| --- | --- |
| `backend/common` | Base ORM, repository, exception và formatter dùng chung; không phụ thuộc `core` hoặc module nghiệp vụ. |
| `backend/core` | Settings, engine và session của metadata database, hạ tầng bảo mật chung. |
| `backend/modules/<module>` | Model, repository, service, schema nhập/xuất, route và lỗi theo nghiệp vụ. |
| `backend/migrations` | Phiên bản schema metadata database; import các model để đối chiếu Alembic. |

Module khác dùng service hoặc repository của module sở hữu dữ liệu; không gọi route nội bộ như một hàm nghiệp vụ. Route đọc request và trả response; service xử lý quy tắc; repository truy vấn bằng session được truyền vào. Caller của service sở hữu transaction và gọi commit khi toàn bộ thao tác thành công.

## Trạng thái hiện tại

`database_connection` là module nghiệp vụ đầu tiên. Đã có bốn model, các migration trong `init_database_module`, bốn repository, service và FastAPI route cho đăng ký kết nối, CRUD và metadata. `backend/__init__.py` hiện chỉ là entrypoint mẫu. `frontend/` là giao diện Next.js đã gọi API của module để quản lý kết nối và xem metadata. API chưa có xác thực/phân quyền.

`data_dictionary` có model, migration, service và API tổng quan theo kết nối, đọc, lưu, tự động điền từ điển mức bảng và mức cột, tham chiếu bảng và cột của `database_connection`. Frontend có tab `Từ điển` để chọn bảng, sửa thông tin bảng và cột, theo dõi tiến độ tự động điền. `backend/agent_package/` chứa phần dùng chung cho mô hình ngôn ngữ: chat model (`get_chat_models.py`), prompt, tool và tài liệu tool.

`business_model` có model, migration, repository, service và API cho tầng dữ liệu, miền nghiệp vụ, bố cục canvas và cạnh lineage thủ công/tham chiếu. `data_lineage` lưu phép biến đổi từ nhiều bảng nguồn, phụ thuộc cột và đọc đồ thị data flow; SQL chỉ được phân tích để xem trước, không thực thi. Hai module tham chiếu metadata của `database_connection`; giao diện Data Lineage là tab `Dòng dữ liệu` của frontend.

`metric_management` lưu metric SQL tự tạo trên bảng metadata và bản sao metric từ Superset. User/database Superset được lưu theo ID và URL nguồn; database được liên kết tới connection standalone đã đăng ký để tìm bảng tương ứng. Đồng bộ chỉ đọc API Superset và không ghi ngược. Giao diện là tab `Metric` của frontend.

`glossary_management` lưu thuật ngữ và các revision theo connection, liên kết tới bảng/cột/metric bằng khóa ngoại. API duyệt, thu hồi và discovery đã có; frontend là tab `Thuật ngữ`.

`expert_rule_management` lưu rule trên một bảng metadata, điều kiện có cấu trúc và các revision. Bảng ghép nối mỗi revision tới glossary đã duyệt và metric cùng bảng; discovery chỉ trả bản đã duyệt khi các liên kết còn đúng phiên bản. Frontend là tab `Quy tắc`. Xem [dữ liệu glossary](modules/glossary_management/du-lieu.md).

`own_knowledge` nhận câu hỏi làm rõ từ AI Agent, chỉ ghi định nghĩa riêng sau khi người dùng xác nhận, và cung cấp API để admin review hoặc chuyển thành glossary/metric/expert rule. Dữ liệu thuộc một `user_id` và connection. AI Agent và admin gọi API bằng hai khóa dịch vụ riêng; chat runtime phải lấy `user_id` từ phiên đăng nhập đáng tin cậy. Xem [module own knowledge](modules/own_knowledge/README.md).

`conversation` lưu lịch sử trò chuyện: hội thoại theo `user_id` và connection, các lượt hỏi đáp (câu hỏi, câu trả lời, bước, kết quả truy vấn) và đánh giá. API CRUD và service ghi lượt (`start`, `begin_turn`, `complete_turn`) đã có; route chat của `text2sql` ghi mỗi lượt qua service này khi request có `user_id` (lịch sử gửi LLM lấy từ lượt đã lưu). Route chat hiện chưa che PII nên `results` lưu dòng thô. `user_id` do client gửi, chưa xác thực. Xem [module conversation](modules/conversation/README.md).

`text2sql` dựng chỉ mục Qdrant cho sáu loại tri thức (bảng, cột, metric, glossary, expert rule, tri thức riêng) và truy hồi metric. Module theo cấu trúc chung: `repositories/` (`QdrantRepository`, `IngestionJobRepository`), `services/` (builder theo topic, ingestion, trigger, retrieve, rerank, chat, agent text2sql), `schemas/`, `routes/`, `utils/` (`exceptions.py`, `topics.py`), `dependencies.py` và `worker.py`. Backend ghi job vào hàng đợi (bảng ở schema `technical`) trong cùng transaction với thay đổi của người dùng; service `ingestion-worker` chạy cùng image backend, lấy job song song theo topic và tự phát lịch. Embedding dùng `backend/agent_package/get_embedding_models.py`. Xem [worker và hàng đợi](modules/text2sql/worker-ingestion.md). Phần hỏi đáp cũ (pipeline chat, `ask_data`, chạy metric, truy vấn nhiều bảng) và MCP server đã gỡ ngày 2026-11-19; route chat mới chạy một graph LangGraph: hiểu câu hỏi, rồi agent gọi công cụ trả lời từng câu đơn (SQL dựng sẵn cho metric hoặc SQL do LLM viết qua bộ kiểm tra, chạy chỉ đọc trên database nguồn), hỏi lại người dùng khi thiếu thông tin; `/chat/stream` stream từng bước qua SSE cho tab `Hỏi dữ liệu`. Xem [hỏi đáp](modules/text2sql/api-chat.md).

Các model database hiện có kế thừa `BaseModel` trong `common`, dùng ID UUID v7 và timestamps. Revision mới chuyển ID số nguyên đã tạo bởi các migration đầu sang UUID v7 cùng các khóa ngoại liên quan.
