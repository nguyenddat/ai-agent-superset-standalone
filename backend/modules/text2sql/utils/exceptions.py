from backend.common.base_exceptions import (
    AppError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)


class Text2SqlConnectionNotFound(NotFoundError):
    abstract = False
    code = "text2sql_connection_not_found"
    message = "Không tìm thấy connection."


class Text2SqlIndexUnavailable(ServiceUnavailableError):
    abstract = False
    code = "text2sql_index_unavailable"
    message = "Không thể truy cập chỉ mục Text2SQL."


class Text2SqlRerankUnavailable(ServiceUnavailableError):
    abstract = False
    code = "text2sql_rerank_unavailable"
    message = "Không thể xếp hạng lại kết quả."


class Text2SqlAgentUnavailable(ServiceUnavailableError):
    abstract = False
    code = "text2sql_agent_unavailable"
    message = "Không thể gọi mô hình ngôn ngữ để xử lý câu hỏi."


class Text2SqlInvalidRequest(ValidationError):
    abstract = False
    code = "text2sql_invalid_request"
    message = "Yêu cầu không hợp lệ."


class Text2SqlQueryFailed(ServiceUnavailableError):
    abstract = False
    code = "text2sql_query_failed"
    message = "Không thể thực hiện truy vấn trên database nguồn."


class Text2SqlClarificationNotFound(NotFoundError):
    abstract = False
    code = "text2sql_clarification_not_found"
    message = "Câu hỏi lại không còn hoặc đã hết hạn; hãy đặt lại câu hỏi."


class Text2SqlClientDisconnected(AppError):
    abstract = False
    status = 499
    code = "client_disconnected"
    message = "Người dùng đã ngắt kết nối trước khi có câu trả lời."


class Text2SqlChartInvalid(ValidationError):
    abstract = False
    code = "text2sql_chart_invalid"
    message = "Biểu đồ không hợp lệ."
