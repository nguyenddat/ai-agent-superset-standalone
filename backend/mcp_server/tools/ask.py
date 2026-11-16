import threading
import time as clock
from typing import Annotated
from uuid import UUID

from mcp.server import MCPServer
from mcp.server.mcpserver import Context, Elicit, ElicitationResult, Resolve
from pydantic import Field

from backend.modules.text2sql.chat.schemas import AskResult
from backend.modules.text2sql.chat.service import AskService, PreparedAsk, execute_ask
from backend.modules.text2sql.query.service import QueryService

from .common import ConnectionId, QuestionText, clean_question, detail_session, run_blocking, search_clients
from .query import NOT_SUPPORTED, PiiConsent, client_can_elicit, confirmation_of, pii_message

CACHE_SECONDS = 120
CACHE_SIZE = 64
_cache: dict[tuple, tuple[float, PreparedAsk]] = {}
_lock = threading.Lock()


def _key(connection_id: UUID, question: str, user_id: str | None) -> tuple:
    return connection_id, question.strip(), (user_id or "").strip()


def run_ask_prepare(connection_id: UUID, question: str, user_id: str | None) -> PreparedAsk:
    key = _key(connection_id, question, user_id)
    with _lock:
        cached = _cache.get(key)
        if cached is not None and cached[0] > clock.monotonic():
            return cached[1]
    with search_clients(True) as (index, embedding, reranker), detail_session() as session:
        prepared = AskService(session, index, embedding, reranker=reranker).prepare(connection_id, question, user_id)
    with _lock:
        if len(_cache) >= CACHE_SIZE:
            _cache.pop(next(iter(_cache)))
        _cache[key] = (clock.monotonic() + CACHE_SECONDS, prepared)
    return prepared


def run_ask_execute(prepared: PreparedAsk, confirmation: str) -> AskResult:
    with detail_session() as session:
        query_service = QueryService(session)
        source_url = query_service.resolve_source(prepared.connection_id) if prepared.status == "ready" else None
    return execute_ask(prepared, query_service, source_url, confirmation)


async def ask_consent(
    ctx: Context, connection_id: UUID, question: str, user_id: str | None,
) -> Elicit[PiiConsent] | str | None:
    prepared = await run_blocking(run_ask_prepare, connection_id, clean_question(question), user_id)
    if prepared.status != "ready" or not prepared.pii_columns:
        return None
    if not client_can_elicit(ctx):
        return NOT_SUPPORTED
    return Elicit(message=pii_message(prepared.pii_columns), schema=PiiConsent)


async def ask_data(
    connection_id: ConnectionId,
    question: QuestionText,
    consent: Annotated[ElicitationResult[PiiConsent], Resolve(ask_consent)],
    user_id: Annotated[
        str | None,
        Field(max_length=255, description="ID người dùng đang hỏi, để dùng cách hiểu riêng của họ (nếu có)."),
    ] = None,
) -> AskResult:
    confirmation = confirmation_of(consent)
    prepared = await run_blocking(run_ask_prepare, connection_id, clean_question(question), user_id)
    return await run_blocking(run_ask_execute, prepared, confirmation)


def register_ask_tools(server: MCPServer) -> None:
    server.tool(
        name="ask_data",
        description=(
            "Trả lời một câu hỏi số liệu bằng MỘT lời gọi, theo luồng cố định của hệ thống: (1) truy hồi thuật ngữ và "
            "quy tắc chuyên gia theo câu hỏi gốc, (2) viết lại câu hỏi theo thuật ngữ chuẩn, (3) chọn metric (ưu tiên "
            "metric đã được thuật ngữ hoặc quy tắc liên kết), (4) lập kế hoạch truy vấn, tự áp điều kiện của mọi quy "
            "tắc gắn với metric, rồi chạy truy vấn chỉ đọc và che dữ liệu cá nhân. Hãy dùng tool này đầu tiên cho mọi "
            "câu hỏi số liệu. Kết quả có status: answered (có số liệu, kèm quy tắc đã áp dụng và giả định), "
            "needs_clarification (cần hỏi lại người dùng) hoặc no_metric (chưa có metric phù hợp, trả kèm các bảng "
            "liên quan). Khi no_metric, không bịa số liệu: dùng find_fields, plan_join rồi query_dataset."
        ),
    )(ask_data)
