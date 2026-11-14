from mcp.server import MCPServer


mcp = MCPServer(
    name="Superset AI",
    instructions=(
        "Server này đang ở giai đoạn nền. Chưa có tool hoặc resource. "
        "Các khả năng truy xuất ngữ nghĩa sẽ được thêm sau khi hoàn thiện embedding và RAG."
    ),
)
