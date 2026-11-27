# backend/

Gói Python của dịch vụ text2sql: FastAPI, SQLAlchemy, Alembic, LangGraph. Điểm vào `backend/main.py` gắn 11 router dưới `/api/v1`. Chạy từ gốc repo (xem [README gốc](../README.md)):

```bash
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
uv run python -m backend.modules.text2sql.worker     # ingestion-worker
```

## Thư mục

| Thư mục | Nội dung |
|---|---|
| `modules/` | Các mô-đun nghiệp vụ, mỗi mô-đun có `routes/`, `services/`, `repositories/`, `schemas/`, `models/`; tài liệu ở `docs/handbook/modules/<tên>/README.md` |
| `common/` | Base ORM, repository, exception, định dạng dữ liệu, `charts/` (danh mục và kiểm tra biểu đồ) |
| `core/` | `setting.py` (đọc `.env`), `database.py` (engine, session) |
| `agent_package/` | Mọi lời gọi LLM và embedding dùng chung (OpenRouter, langchain-openai), `tool_agent.py`, `prompts/` |
| `migrations/` | Revision Alembic của cơ sở dữ liệu metadata, nhóm theo `versions/init_<module>_module/` |
| `mcp_server/` | Không còn mã nguồn: MCP server đã gỡ ngày 2026-11-19 |

## Mô-đun (`modules/`)

| Mô-đun | Vai trò |
|---|---|
| `database_connection` | Kết nối tới cơ sở dữ liệu nguồn (URI mã hóa Fernet) và bản sao metadata: schema, bảng, view, cột |
| `data_dictionary` | Mô tả nghiệp vụ của bảng và cột; tự điền bằng AI |
| `business_model` | Tầng dữ liệu, miền nghiệp vụ, canvas, cạnh lineage |
| `data_lineage` | Phép biến đổi nhiều bảng nguồn, đồ thị luồng dữ liệu; SQL chỉ phân tích để xem trước |
| `metric_management` | Metric SQL tự tạo và bản sao metric từ Superset (đồng bộ một chiều, chỉ đọc) |
| `glossary_management`, `expert_rule_management` | Thuật ngữ và quy tắc chuyên gia, có revision |
| `own_knowledge` | Câu hỏi làm rõ từ agent, tri thức riêng theo người dùng và kết nối, admin duyệt |
| `conversation` | Lịch sử hội thoại, lượt hỏi đáp, đánh giá |
| `text2sql` | Chỉ mục Qdrant, truy hồi, chat (LangGraph), worker ingestion |

Quy ước chung và kiến trúc: [docs/handbook/kien-truc.md](../docs/handbook/kien-truc.md), [AGENTS.md](../AGENTS.md).
