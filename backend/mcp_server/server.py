from mcp.server import MCPServer

from backend.modules.model_registry import register_all_models

from .prompts import register_prompts
from .resources import register_resources
from .tools import register_tools

register_all_models()

mcp = MCPServer(
    name="Superset AI",
    instructions=(
        "Với mọi câu hỏi số liệu, gọi ask_data trước: nó tự viết lại câu hỏi theo thuật ngữ và quy tắc chuyên gia, "
        "chọn metric, áp quy tắc và chạy truy vấn chỉ đọc trong một lời gọi. Nếu status là needs_clarification thì hỏi "
        "lại người dùng. Nếu no_metric thì không bịa số liệu: dùng find_fields để tìm cột và bảng chứa chúng, "
        "plan_join để xem cách nối (truyền root_table_id theo grain câu hỏi), rồi query_dataset để chạy truy vấn nhiều "
        "bảng; nếu plan_join hoặc query_dataset báo not_declared thì báo người dùng bổ sung khai báo quan hệ trong "
        "data dictionary, không tự nối bảng. Các tool search_*, get_* và query_metric "
        "dùng để khám phá thêm khi cần: search_tables, search_columns, search_metrics, search_glossary_terms, "
        "search_expert_rules, search_own_knowledge. Kết quả của search_tables và search_columns đã gồm toàn bộ mô tả "
        "có cấu trúc. Đặt rerank=true chỉ khi kết quả đầu tiên mơ hồ."
    ),
)

register_tools(mcp)
register_resources(mcp)
register_prompts(mcp)
