# Handbook

Handbook ghi lại cấu trúc và quy ước đang dùng trong repository standalone. Mô tả **đã triển khai** dựa trên code hiện tại; phần chưa có code được đánh dấu **dự kiến**.

## Quy ước chung

- [Kiến trúc](kien-truc.md): ranh giới backend, frontend và các lớp backend.
- [Quy ước code](quy-uoc-code.md): tên, kiểu dữ liệu, test và commit.
- [Dữ liệu và migration](du-lieu-va-migration.md): metadata database, database nguồn và Alembic.
- [Hành vi API](hanh-vi-api.md): transaction, lỗi, định dạng dữ liệu và cấu trúc luồng API.
- [Frontend](frontend/README.md): Next.js, điều hướng và trạng thái tích hợp backend.
- [Docker](docker.md): build image, Compose, vận hành stack cục bộ và simulation weather warehouse.
- [MCP server](mcp-server.md): cấu trúc theo tools/resources/prompts, 15 tool: 10 tool tìm (`search_*`) và xem chi tiết (`get_*`) bảng, cột, metric, thuật ngữ, quy tắc, tri thức riêng, `query_metric` chạy metric chỉ đọc, `ask_data` hỏi đáp một lần gọi ([luồng hỏi đáp](modules/text2sql/ask-flow.md)), `find_fields`, `plan_join` và `query_dataset` truy vấn nhiều bảng khi chưa có metric ([tìm trường và nối bảng](modules/text2sql/find-fields-join.md), [dựng truy vấn](modules/text2sql/build-query.md), [dataset truy vấn](modules/text2sql/query-datasets.md)), có che dữ liệu cá nhân, tham số `rerank`, cách chạy stdio và HTTP cục bộ.

## Module

| Module | Tài liệu | Trạng thái |
| --- | --- | --- |
| `database_connection` | [Tổng quan module](modules/database_connection/README.md) | Model, migration, repository, service và API FastAPI đã có. |
| `data_dictionary` | [Tổng quan module](modules/data_dictionary/README.md) | Model, migration, API đọc, lưu, tự động điền (AI, streaming) và giao diện mô tả bảng, cột đã có; quan hệ đã kiểm tra dữ liệu giữa các bảng dự kiến. |
| `business_model` | [Tổng quan module](modules/business_model/README.md) | Model, migration, service và API cho tầng dữ liệu, miền nghiệp vụ, canvas và lineage đã có; giao diện dự kiến. |
| `data_lineage` | [Tổng quan module](modules/data_lineage/README.md) | Migration và API xem trước SQL, khai báo phép biến đổi và đọc đồ thị đã có; giao diện là tab `Dòng dữ liệu`. |
| `metric_management` | [Tổng quan module](modules/metric_management/README.md) | CRUD metric tự tạo và đồng bộ một chiều metric, user, database từ Superset đã có; giao diện là tab `Metric`. |
| `glossary_management` | [Tổng quan module](modules/glossary_management/README.md) | Migration, API và tab `Thuật ngữ` đã có. |
| `expert_rule_management` | [Tổng quan module](modules/expert_rule_management/README.md) | Migration, API và tab `Quy tắc` đã có. |
| `own_knowledge` | [Tổng quan module](modules/own_knowledge/README.md) | API Agent push câu hỏi làm rõ, lưu tri thức riêng sau xác nhận, admin review và chuyển thành bản ghi hệ thống đã có; chat runtime và frontend dự kiến. |
| `conversation` | [Tổng quan module](modules/conversation/README.md) | Migration, service và API CRUD lịch sử trò chuyện (hội thoại, lượt hỏi đáp, đánh giá) theo `user_id` và connection đã có; pipeline chat ghi lượt, hỏi nối tiếp và chọn cách nối ở lượt sau đã có; frontend dự kiến. |
| `text2sql` | [Luồng dùng metric có sẵn](modules/text2sql/README.md) | `query_metric` (chạy metric chỉ đọc, che PII bằng Presidio) và `ingestion` sáu topic (bảng, cột, metric, glossary, quy tắc, tri thức riêng) với hàng đợi, worker song song, trigger tự động và `retrieve` top K metric đã có ở backend; `ask_data` hỏi đáp một lần gọi, và khi chưa có metric thì `find_fields`, `plan_join`, `query_dataset` truy vấn nhiều bảng có lưu dataset dùng lại; route chat streaming `POST /api/v1/text2sql/chat` ([luồng chat](modules/text2sql/chat-flow.md)) và câu hỏi gợi ý `GET /api/v1/text2sql/suggestions` ([gợi ý](modules/text2sql/suggestions.md)) ghép các agent ở [gói agent dùng chung](modules/agent_package.md). |

Khi thêm module mới, tạo `modules/<ten_module>/README.md`, tài liệu dữ liệu và một file riêng cho từng luồng API. Cập nhật mục lục này cùng thay đổi code.
