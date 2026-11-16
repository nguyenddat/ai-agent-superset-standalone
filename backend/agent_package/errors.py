from backend.common.base_exceptions import ServiceUnavailableError


class AgentUnavailableError(ServiceUnavailableError):
    abstract = False
    code = "agent_unavailable"
    message = "Không thể gọi mô hình ngôn ngữ."
