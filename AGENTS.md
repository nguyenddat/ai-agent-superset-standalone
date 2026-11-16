# Hướng dẫn làm việc với AI Agent Superset Standalone

## Phạm vi

Repository này phát triển ứng dụng độc lập với backend Python và frontend riêng. `ai-agent-superset-extension` là nguồn tham khảo kiến trúc; không sửa repository đó trừ khi người dùng yêu cầu rõ.

## Đọc handbook trước khi sửa code

- [Mục lục handbook](docs/handbook/README.md)
- [Kiến trúc](docs/handbook/kien-truc.md)
- [Quy ước code](docs/handbook/quy-uoc-code.md)
- [Dữ liệu và migration](docs/handbook/du-lieu-va-migration.md)
- [Hành vi API](docs/handbook/hanh-vi-api.md)

Khi thay đổi hành vi, cấu trúc dữ liệu hoặc quy ước, cập nhật handbook trong cùng thay đổi. Mỗi module trong `backend/modules/<ten_module>/` có thư mục tương ứng `docs/handbook/modules/<ten_module>/`. Mỗi luồng API của module có file riêng; ghi rõ trạng thái **đã triển khai** hoặc **dự kiến**.

## Cấu trúc repository

- `backend/common/`: base model, repository, exception và formatter dùng chung.
- `backend/core/`: cấu hình, engine và session của metadata database, hạ tầng bảo mật.
- `backend/modules/`: các nghiệp vụ, mỗi module một thư mục (xem mục lục handbook); `text2sql` gồm cả worker ingestion chạy bằng `python -m backend.modules.text2sql.worker` và route chat streaming SSE `POST /api/v1/text2sql/chat` (pipeline ở `text2sql/chat/`, xem [luồng chat](docs/handbook/modules/text2sql/chat-flow.md)); `conversation` lưu lịch sử trò chuyện (API `/api/v1/conversations`; route chat ghi lượt qua `ConversationService` khi có `user_id`, xem [module conversation](docs/handbook/modules/conversation/README.md)).
- `backend/mcp_server/`: MCP server, chia thư mục `tools/`, `resources/`, `prompts/`; hiện có 15 tool: tìm và xem bảng, cột, metric, thuật ngữ, quy tắc, tri thức riêng, `query_metric` chạy metric (chỉ đọc, che PII), `ask_data` (luồng hỏi đáp cố định), `find_fields` và `plan_join` (tìm trường, tính cách nối bảng), `query_dataset` (truy vấn nhiều bảng do server tự nối, lưu dataset dùng lại).
- `backend/agent_package/`: chat model và hàm gọi dùng chung (`get_chat_models.py`: `invoke_structured`, `stream_structured`, `structured_model`, `build_messages`, `stream_text`), embedding model (`get_embedding_models.py`), prompt (`prompts/`), agent gọi mô hình một lượt (`agents/`: `QuestionRewriteAgent`, `QueryPlanAgent`, `DatasetPlanAgent`, `AnalysisAgent` cùng schema đầu ra; lỗi `AgentUnavailableError`), dùng chung cho các tính năng AI; xem [gói agent dùng chung](docs/handbook/modules/agent_package.md). Module nghiệp vụ gọi agent chứ không chứa lời gọi mô hình; `agent_package` không import từ `backend/modules`.
- `backend/migrations/`: Alembic; script của module nằm trong `versions/init_<ten_module>_module/`. Module `database_connection` hiện dùng tên thư mục `init_database_module`; `data_dictionary` dùng `init_data_dictionary_module`; `text2sql` dùng `init_text2sql_module` và đặt bảng kỹ thuật trong schema `technical`; `conversation` dùng `init_conversation_module`.
- `frontend/`: ứng dụng Next.js App Router độc lập, khởi tạo bằng `create-next-app`; hướng dẫn tại [handbook frontend](docs/handbook/frontend/README.md).
- `docs/handbook/`: quy ước và luồng xử lý kỹ thuật.
- `docs/reports/`: báo cáo, tách khỏi handbook.
- `backend/Dockerfile`, `frontend/Dockerfile`, `compose.yaml`: image và stack chạy cục bộ (gồm `ingestion-worker`).

## Làm việc và kiểm tra

Chạy `uv` và Alembic từ gốc repository. Python yêu cầu 3.14; thêm dependency bằng `uv add` để cập nhật `pyproject.toml` và `uv.lock`. `DATABASE_URL` trỏ đến metadata database của ứng dụng, không phải database nguồn do người dùng đăng ký. Không đưa mật khẩu, URI chứa mật khẩu hoặc khóa API thật vào code, log, test hay tài liệu.

Đọc model và migration hiện tại trước khi sửa schema. Thêm model vào `models/__init__.py` để Alembic autogenerate nhận diện. Không sửa revision đã được phát hành; tạo revision mới và kiểm tra upgrade/downgrade khi thay đổi schema. Repository không tự commit transaction; caller quyết định commit, `get_database()` rollback khi có exception và luôn đóng session.

Không viết docstring cho module và hàm trừ khi người dùng yêu cầu rõ. Giữ type hints và tên hàm đủ rõ nghĩa.

Viết tài liệu Markdown bằng tiếng Việt có dấu, UTF-8. Trước khi hoàn tất, kiểm tra link nội bộ, `git diff --check` và các lệnh liên quan đến phần đã sửa. Commit theo Conventional Commits: `<type>(<scope>): <description>`.
