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
- `backend/modules/`: các nghiệp vụ, mỗi module một thư mục (xem mục lục handbook); `text2sql` gồm chỉ mục vector (ingestion, retrieve, rerank), route chat (graph LangGraph: hiểu câu hỏi, agent truy vấn chỉ đọc database nguồn và trả lời) và worker ingestion chạy bằng `python -m backend.modules.text2sql.worker`; `conversation` lưu lịch sử trò chuyện (API `/api/v1/conversations`, xem [module conversation](docs/handbook/modules/conversation/README.md)).
- `backend/agent_package/`: chat model dùng chung (`get_chat_models.py`: `get_chat_model`, `structured_model`, `build_messages`), embedding model (`get_embedding_models.py`) và prompt (`prompts/`); xem [gói agent dùng chung](docs/handbook/modules/agent_package.md). `agent_package` không import từ `backend/modules`.
- `backend/migrations/`: Alembic; script của module nằm trong `versions/init_<ten_module>_module/`. Module `database_connection` hiện dùng tên thư mục `init_database_module`; `data_dictionary` dùng `init_data_dictionary_module`; `text2sql` dùng `init_text2sql_module` và đặt bảng kỹ thuật trong schema `technical`; `conversation` dùng `init_conversation_module`.
- `frontend/`: ứng dụng Next.js App Router độc lập, khởi tạo bằng `create-next-app`; hướng dẫn tại [handbook frontend](docs/handbook/frontend/README.md).
- `docs/handbook/`: quy ước và luồng xử lý kỹ thuật.
- `docs/reports/`: báo cáo, tách khỏi handbook.
- `scripts/`: công cụ cho người phát triển, không thuộc ứng dụng; `scripts/text2sql_eval` chạy bộ câu hỏi đánh giá route chat text2sql trên database nguồn và LLM thật (xem [chạy đánh giá thật](docs/handbook/modules/text2sql/danh-gia-chay-that.md)).
- `backend/Dockerfile`, `frontend/Dockerfile`, `compose.yaml`: image và stack chạy cục bộ (gồm `ingestion-worker`).

## Làm việc và kiểm tra

Chạy `uv` và Alembic từ gốc repository. Python yêu cầu 3.14; thêm dependency bằng `uv add` để cập nhật `pyproject.toml` và `uv.lock`. `DATABASE_URL` trỏ đến metadata database của ứng dụng, không phải database nguồn do người dùng đăng ký. Không đưa mật khẩu, URI chứa mật khẩu hoặc khóa API thật vào code, log, test hay tài liệu.

Đọc model và migration hiện tại trước khi sửa schema. Thêm model vào `models/__init__.py` để Alembic autogenerate nhận diện. Không sửa revision đã được phát hành; tạo revision mới và kiểm tra upgrade/downgrade khi thay đổi schema. Repository không tự commit transaction; caller quyết định commit, `get_database()` rollback khi có exception và luôn đóng session.

Giữ type hints và tên hàm đủ rõ nghĩa. Viết tài liệu Markdown bằng tiếng Việt có dấu, UTF-8. Commit theo Conventional Commits: `<type>(<scope>): <description>`.

## Quy trình và lệnh kiểm tra

Repository theo quy trình sdlc (`.claude/sdlc.json`, rule card trong `.claude/rules/`, review theo `REVIEW.md`): gọi skill `sdlc` trước mỗi thay đổi code.

Trước khi hoàn tất, chạy `scripts/verify.sh` (khoảng 80 giây, cần `uv` và Node 22+): `git diff --check`, ruff (dòng 120 ký tự, thứ tự import), `scripts/check_conventions.py` (không docstring, không `os.getenv` ngoài `setting.py`, `agent_package` không import `backend.modules`, link nội bộ, thư mục handbook của module), 374 test backend với database, Qdrant và khóa LLM bị ghi đè nên không chạm stack đang chạy, rồi `lint`, `typecheck`, `test:charts` của frontend. Kết quả tốt:

```text
All checks passed!
conventions ok (380 files)
Ran 374 tests in 24s
OK (skipped=7)
# pass 82
```

Chưa có CI. Chỉ chạy bằng tay: `npx next build`, test Qdrant (`QDRANT_TEST_URL`), Alembic upgrade/check/downgrade trên database tạm và bộ đánh giá thật `scripts/text2sql_eval`.
