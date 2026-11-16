from backend.common.base_exceptions import ConflictError, NotFoundError, ServiceUnavailableError, ValidationError


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


class Text2SqlEntityNotFound(NotFoundError):
    abstract = False
    code = "text2sql_entity_not_found"
    message = "Không tìm thấy mục này hoặc mục không còn khả dụng."


class Text2SqlInvalidRequest(ValidationError):
    abstract = False
    code = "text2sql_invalid_request"
    message = "Yêu cầu không hợp lệ."


class Text2SqlMetricNotRunnable(ValidationError):
    abstract = False
    code = "text2sql_metric_not_runnable"
    message = "Metric này chưa thể dùng để truy vấn."


class Text2SqlQueryTimeout(ServiceUnavailableError):
    abstract = False
    code = "text2sql_query_timeout"
    message = "Truy vấn vượt quá thời gian cho phép."


class Text2SqlQueryFailed(ServiceUnavailableError):
    abstract = False
    code = "text2sql_query_failed"
    message = "Không thể thực hiện truy vấn trên database nguồn."



class Text2SqlChatTurnInvalid(ValidationError):
    abstract = False
    status = 422
    code = "text2sql_chat_turn_invalid"
    message = "Yêu cầu tiếp tục hội thoại không hợp lệ."


class Text2SqlJoinChoiceOutdated(ConflictError):
    abstract = False
    code = "text2sql_join_choice_outdated"
    message = "Cách nối đã chọn không còn trong các cách nối hiện tại; hãy hỏi lại để xem các cách nối mới."
