from backend.common.base_exceptions import (
    ConflictError, NotAuthenticatedError, NotAuthorizedError, NotFoundError, ServiceUnavailableError, ValidationError,
)


class OwnKnowledgeValidationError(ValidationError):
    code = "own_knowledge_invalid"
    message = "Dữ liệu own knowledge không hợp lệ."


class OwnKnowledgeConflictError(ConflictError):
    code = "own_knowledge_conflict"
    message = "Dữ liệu đã thay đổi; hãy tải lại trước khi lưu."


class OwnKnowledgeNotFoundError(NotFoundError):
    code = "own_knowledge_not_found"
    message = "Không tìm thấy nội dung own knowledge."


class OwnKnowledgeUnauthorizedError(NotAuthenticatedError):
    code = "own_knowledge_unauthorized"
    message = "Thiếu hoặc sai khóa truy cập own knowledge."


class OwnKnowledgeForbiddenError(NotAuthorizedError):
    code = "own_knowledge_forbidden"
    message = "Không có quyền xem nội dung của người dùng này."


class OwnKnowledgeNotConfiguredError(ServiceUnavailableError):
    code = "own_knowledge_not_configured"
    message = "Chưa cấu hình khóa dịch vụ own knowledge."
