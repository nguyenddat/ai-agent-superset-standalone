# MCP server

**Trạng thái: đã triển khai phần nền.** `backend/mcp_server/` tạo MCP server bằng Python SDK chính thức. Server hiện có tên và khả năng bắt tay giao thức; danh sách tool và resource còn trống. Chưa có embedding, RAG, API truy xuất hoặc thao tác CRUD qua MCP.

Chạy từ gốc repository bằng stdio để MCP host khởi động như một tiến trình con:

```powershell
uv run superset-ai-mcp
```

Cấu hình MCP host với lệnh `uv`, các tham số `run`, `superset-ai-mcp` và thư mục làm việc là gốc repository. Không ghi thông tin thường ra stdout vì stdout là luồng giao thức.

Để thử Streamable HTTP trên cùng máy:

```powershell
uv run superset-ai-mcp --transport streamable-http --host 127.0.0.1 --port 8001
```

Endpoint là `http://127.0.0.1:8001/mcp`. Chế độ HTTP chỉ chấp nhận địa chỉ loopback vì chưa có xác thực cho MCP. Không mở cổng ra mạng ngoài. Server MCP chạy độc lập với FastAPI; giai đoạn hiện tại chưa gọi backend hoặc database.

Kiểm tra nền bằng `uv run python -m unittest tests.test_mcp_server`. Bài kiểm tra kết nối trong bộ nhớ và qua stdio, rồi xác nhận `tools/list` trả danh sách rỗng. Phần tiếp theo sẽ xác định hợp đồng embedding, chỉ mục và RAG retrieval trước khi đăng ký tool.
