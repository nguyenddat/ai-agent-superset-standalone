# Handbook

Handbook ghi lại cấu trúc và quy ước đang dùng trong repository standalone. Mô tả **đã triển khai** dựa trên code hiện tại; phần chưa có code được đánh dấu **dự kiến**.

## Quy ước chung

- [Kiến trúc](kien-truc.md): ranh giới backend, frontend và các lớp backend.
- [Quy ước code](quy-uoc-code.md): tên, kiểu dữ liệu, test và commit.
- [Dữ liệu và migration](du-lieu-va-migration.md): metadata database, database nguồn và Alembic.
- [Hành vi API](hanh-vi-api.md): transaction, lỗi, định dạng dữ liệu và cấu trúc luồng API.

## Module

| Module | Tài liệu | Trạng thái |
| --- | --- | --- |
| `database_connection` | [Tổng quan module](modules/database_connection/README.md) | Model và migration đã có; API đang thiết kế. |

Khi thêm module mới, tạo `modules/<ten_module>/README.md`, tài liệu dữ liệu và một file riêng cho từng luồng API. Cập nhật mục lục này cùng thay đổi code.
