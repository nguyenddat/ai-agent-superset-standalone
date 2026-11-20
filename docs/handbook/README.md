# Handbook

Handbook ghi lại cấu trúc và quy ước đang dùng trong repository standalone. Mô tả **đã triển khai** dựa trên code hiện tại; phần chưa có code được đánh dấu **dự kiến**.

## Quy ước chung

- [Kiến trúc](kien-truc.md): ranh giới backend, frontend và các lớp backend.
- [Quy ước code](quy-uoc-code.md): tên, kiểu dữ liệu, test và commit.
- [Dữ liệu và migration](du-lieu-va-migration.md): metadata database, database nguồn và Alembic.
- [Hành vi API](hanh-vi-api.md): transaction, lỗi, định dạng dữ liệu và cấu trúc luồng API.
- [Frontend](frontend/README.md): Next.js, điều hướng và trạng thái tích hợp backend.
- [Docker](docker.md): build image, Compose, vận hành stack cục bộ và simulation weather warehouse.

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
| `conversation` | [Tổng quan module](modules/conversation/README.md) | Migration, service và API CRUD lịch sử trò chuyện (hội thoại, lượt hỏi đáp, đánh giá) theo `user_id` và connection đã có; pipeline chat ghi lượt đã gỡ cùng phần hỏi đáp của `text2sql`. |
| `text2sql` | [Chỉ mục tri thức và truy hồi](modules/text2sql/README.md) | `ingestion` sáu topic (bảng, cột, metric, glossary, quy tắc, tri thức riêng) với hàng đợi, worker song song, trigger tự động và `retrieve` top K metric đã có ở backend. Phần hỏi đáp (chat, `ask_data`, chạy metric, truy vấn nhiều bảng) và MCP server đã gỡ ngày 2026-11-19 để làm lại. |

Khi thêm module mới, tạo `modules/<ten_module>/README.md`, tài liệu dữ liệu và một file riêng cho từng luồng API. Cập nhật mục lục này cùng thay đổi code.
