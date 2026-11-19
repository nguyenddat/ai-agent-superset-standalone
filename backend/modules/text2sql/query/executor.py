import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.pool import NullPool

from ..common.errors import Text2SqlQueryFailed, Text2SqlQueryTimeout

logger = logging.getLogger("text2sql.query")

CONNECT_TIMEOUT_SECONDS = 5
LOCK_TIMEOUT_MS = 3000
QUERY_CANCELED = "57014"
# The Wattprint copilot's scope token: the one home its copilot_ro views may show (they read the
# setting app.copilot_token). Set per request by the chat route; None leaves the setting unset.
SCOPE_TOKEN: ContextVar[str | None] = ContextVar("scope_token", default=None)
# The caller's IANA time zone: days and hours in the SQL are cut in it (default UTC). Validated by
# the chat route before it is set, as it goes into the connection options.
TIME_ZONE: ContextVar[str] = ContextVar("time_zone", default="UTC")


@dataclass(frozen=True)
class RawResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    elapsed_ms: int


def run_read_only(
    url: URL, sql: str, parameters: dict[str, Any], expanding: frozenset[str], max_rows: int, timeout_seconds: int,
) -> RawResult:
    timeout_ms = timeout_seconds * 1000
    options = (
        f"-c default_transaction_read_only=on -c statement_timeout={timeout_ms} -c lock_timeout={LOCK_TIMEOUT_MS} "
        f"-c idle_in_transaction_session_timeout={timeout_ms} -c TimeZone={TIME_ZONE.get()}"
    )
    statement = text(sql).bindparams(*(bindparam(name, expanding=True) for name in expanding))
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
                if (scope_token := SCOPE_TOKEN.get()) is not None:
                    connection.execute(text("SELECT set_config('app.copilot_token', :t, true)"), {"t": scope_token})
                result = connection.execute(statement, parameters)
                columns = list(result.keys())
                rows = [tuple(row) for row in result.fetchmany(max_rows)]
            finally:
                transaction.rollback()
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) == QUERY_CANCELED:
            raise Text2SqlQueryTimeout(
                f"Truy vấn vượt quá {timeout_seconds} giây. Hãy thu hẹp khoảng thời gian hoặc thêm bộ lọc."
            ) from None
        logger.warning("Truy vấn nguồn lỗi: %s", type(error.orig).__name__)
        raise Text2SqlQueryFailed() from None
    except (SQLAlchemyError, OSError, TimeoutError) as error:
        logger.warning("Không kết nối được database nguồn: %s", type(error).__name__)
        raise Text2SqlQueryFailed() from None
    finally:
        engine.dispose()
    return RawResult(columns=columns, rows=rows, elapsed_ms=int((time.monotonic() - started) * 1000))
