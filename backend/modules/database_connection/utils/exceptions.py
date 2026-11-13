from backend.common.base_exceptions import ConflictError, NotFoundError, ServiceUnavailableError, ValidationError


class InvalidConnectionError(ValidationError):
    abstract = False
    status = 422
    code = "invalid_database_connection"
    message = "Thông tin kết nối database không hợp lệ."


class ConnectionAlreadyExistsError(ConflictError):
    abstract = False
    code = "database_connection_exists"
    message = "Tên kết nối database đã tồn tại."


class ConnectionNotFoundError(NotFoundError):
    abstract = False
    code = "database_connection_not_found"
    message = "Không tìm thấy kết nối database."


class SourceDatabaseUnavailableError(ServiceUnavailableError):
    abstract = False
    code = "source_database_unavailable"
    message = "Không thể kết nối đến database nguồn."


class MetadataNotFoundError(NotFoundError):
    abstract = False
    code = "database_metadata_not_found"
    message = "Không tìm thấy metadata được yêu cầu."


class InactiveConnectionError(ConflictError):
    abstract = False
    code = "database_connection_inactive"
    message = "Kết nối database đang bị vô hiệu hóa."
