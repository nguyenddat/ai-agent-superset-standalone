# Quy ước code và tài liệu

## Python và tổ chức module

- Dùng Python 3.14, SQLAlchemy 2.1 và type hints cho hàm, thuộc tính quan trọng.
- Không viết docstring cho module và hàm khi chưa có yêu cầu riêng.
- Đặt tên theo nghiệp vụ: `database_connection`, `selected_schema`, `created_at`; tránh tên viết tắt khó hiểu.
- Giữ dòng code tối đa 120 ký tự. Chỉ tách dòng khi cần để dễ đọc hoặc vượt giới hạn.
- Import trong cùng một module dùng import tương đối (`from ..models import TableDictionary`, `from .semantics import ...`). Import từ module khác, `backend.common`, `backend.core` hoặc `backend.agent_package` dùng đường dẫn đầy đủ. Nhóm import tương đối đặt sau nhóm import tuyệt đối; có thể sắp xếp bằng `uvx ruff check --select I --fix --line-length 120`.
- Một module sở hữu model và truy vấn của nghiệp vụ đó. Repository nhận session, không tự commit. Service không đọc trực tiếp HTTP request.
- Exception cụ thể đặt trong module, kế thừa từ `backend.common.base_exceptions`, có `code` riêng và thông điệp an toàn để trả cho client.
- Biến cấu hình chung đọc qua `backend.core.setting.Config`; không đọc `os.getenv` rải rác trong module.
- Tiến trình không đi qua `backend.main` (worker, MCP server, script) phải gọi `register_all_models()` từ `backend.modules.model_registry` trước khi truy vấn, vì các model tham chiếu bảng của nhau bằng khóa ngoại dạng chuỗi và thiếu một module thì SQLAlchemy không dựng được mapper. Module mới thêm package `models` của nó vào `MODEL_PACKAGES` ở file đó; `env.py` của Alembic dùng cùng danh sách.

## Dữ liệu và định dạng

- Dùng `datetime` có timezone và chuẩn hóa UTC trước khi lưu. Cột thời gian dùng `DateTime(timezone=True)`.
- Dùng `backend.common.utils.type_formatters` khi xuất dữ liệu: datetime ISO 8601 UTC với sáu chữ số phần giây và `Z`; date `YYYY-MM-DD`; UUID và Decimal thành chuỗi; `str`, `int`, `bool` giữ nguyên kiểu.
- Không suy đoán timezone của datetime không có timezone. Không chuyển Decimal sang float khi độ chính xác có ý nghĩa.
- Không ghi secret thật vào log hoặc tài liệu. File `.env` ở gốc repository bị Git bỏ qua.

## Kiểm tra và commit

Chạy lệnh từ gốc repository. Dùng `uv run python` để kiểm tra code Python; khi sửa model hoặc migration, kiểm tra Alembic upgrade, `alembic check` và downgrade trên database tạm. Chỉ chạy trên PostgreSQL thật khi có cấu hình database thử nghiệm rõ ràng.

Commit dùng Conventional Commits: `<type>(<scope>): <description>`, ví dụ `feat(database): add metadata sync` hoặc `docs(handbook): describe connection flow`.

Tài liệu trong `docs/` và `AGENTS.md` viết tiếng Việt có dấu, mã hóa UTF-8. Dùng link tương đối cho file trong repository. Mỗi tài liệu API ghi ngày hoặc trạng thái triển khai khi cập nhật, và phân biệt hành vi hiện có với quyết định thiết kế.
