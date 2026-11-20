import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError, DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.agent_package.tool_agent import ToolError
from backend.core.setting import config
from backend.modules.database_connection.models import DatabaseConnection

from ..utils.exceptions import (
    Text2SqlConnectionNotFound,
    Text2SqlInvalidRequest,
    Text2SqlQueryFailed,
)

logger = logging.getLogger("text2sql.query")

CONNECT_TIMEOUT_SECONDS = 5
LOCK_TIMEOUT_MS = 3000
QUERY_CANCELED = "57014"
CONNECTION_ERROR_CLASS = "08"


@dataclass(frozen=True)
class QueryRows:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    truncated: bool
    elapsed_ms: int


def source_url(session: Session, connection_id: UUID) -> URL:
    connection = session.get(DatabaseConnection, connection_id)
    if connection is None:
        raise Text2SqlConnectionNotFound()
    if not connection.is_active:
        raise Text2SqlInvalidRequest("Connection đang tạm dừng nên chưa thể truy vấn.")
    try:
        key = config.require_connection_encryption_key()
        return make_url(Fernet(key.encode()).decrypt(connection.uri_ciphertext.encode()).decode("utf-8"))
    except (InvalidToken, UnicodeError, ValueError, ArgumentError, RuntimeError) as error:
        logger.warning("Không giải mã được URI của connection: %s", type(error).__name__)
        raise Text2SqlQueryFailed() from None


def _database_message(error: DBAPIError) -> str:
    diagnostic = getattr(error.orig, "diag", None)
    message = getattr(diagnostic, "message_primary", None) or str(error.orig).splitlines()[0]
    hint = getattr(diagnostic, "message_hint", None)
    return f"{message} (gợi ý: {hint})" if hint else message


def run_read_only(url: URL, sql: str, max_rows: int, timeout_seconds: int) -> QueryRows:
    timeout_ms = timeout_seconds * 1000
    options = (
        f"-c default_transaction_read_only=on -c statement_timeout={timeout_ms} -c lock_timeout={LOCK_TIMEOUT_MS} "
        f"-c idle_in_transaction_session_timeout={timeout_ms} -c TimeZone={config.text2sql_timezone}"
    )
    engine = create_engine(
        url, poolclass=NullPool,
        connect_args={
            "connect_timeout": CONNECT_TIMEOUT_SECONDS, "options": options, "application_name": "superset-ai",
        },
    )
    started = time.monotonic()
    try:
        with engine.connect() as connection:
            connection = connection.execution_options(isolation_level="REPEATABLE READ", postgresql_readonly=True)
            transaction = connection.begin()
            try:
                connection.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
                result = connection.execute(text(sql))
                columns = list(result.keys())
                rows = [tuple(row) for row in result.fetchmany(max_rows + 1)]
            finally:
                transaction.rollback()
    except DBAPIError as error:
        sqlstate = getattr(error.orig, "sqlstate", None) or ""
        if sqlstate == QUERY_CANCELED:
            raise ToolError(
                f"Truy vấn vượt quá {timeout_seconds} giây. Hãy thu hẹp khoảng thời gian, thêm bộ lọc hoặc gộp bớt."
            ) from None
        if error.connection_invalidated or not sqlstate or sqlstate.startswith(CONNECTION_ERROR_CLASS):
            logger.warning("Không kết nối được database nguồn: %s", type(error.orig).__name__)
            raise Text2SqlQueryFailed() from None
        raise ToolError(f"Database báo lỗi {sqlstate}: {_database_message(error)}") from None
    except (SQLAlchemyError, OSError, TimeoutError) as error:
        logger.warning("Không kết nối được database nguồn: %s", type(error).__name__)
        raise Text2SqlQueryFailed() from None
    finally:
        engine.dispose()
    return QueryRows(
        columns=columns, rows=rows[:max_rows], truncated=len(rows) > max_rows,
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )
