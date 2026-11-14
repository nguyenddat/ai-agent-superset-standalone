from backend.common.base_exceptions import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)


class MetricNotFoundError(NotFoundError):
    code = "metric_not_found"
    message = "Không tìm thấy metric."


class InvalidMetricError(ValidationError):
    code = "invalid_metric"
    message = "Metric không hợp lệ."


class MetricAlreadyExistsError(ConflictError):
    code = "metric_exists"
    message = "Tên metric đã tồn tại trên bảng này."


class MetricReadOnlyError(ConflictError):
    code = "metric_read_only"
    message = "Metric đồng bộ từ Superset chỉ được sửa tại Superset."


class SupersetUnavailableError(ServiceUnavailableError):
    code = "superset_unavailable"
    message = "Không thể đọc dữ liệu từ Superset."


class SupersetNotConfiguredError(ValidationError):
    code = "superset_not_configured"
    message = "Chưa cấu hình SUPERSET_URL, SUPERSET_USERNAME và SUPERSET_PASSWORD."


class SupersetDatabaseNotFoundError(NotFoundError):
    code = "superset_database_not_found"
    message = "Không tìm thấy database đã đồng bộ từ Superset."
