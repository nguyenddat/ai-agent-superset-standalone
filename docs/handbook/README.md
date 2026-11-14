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

Khi thêm module mới, tạo `modules/<ten_module>/README.md`, tài liệu dữ liệu và một file riêng cho từng luồng API. Cập nhật mục lục này cùng thay đổi code.
