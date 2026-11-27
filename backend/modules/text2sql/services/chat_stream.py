import asyncio
import logging
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractContextManager
from typing import Any

from backend.common.base_exceptions import AppError
from backend.modules.database_connection.models import DatabaseConnection

from ..repositories.source_query_repository import SCOPE_TOKEN
from ..schemas import ChatIn
from ..utils.exceptions import Text2SqlClientDisconnected, Text2SqlConnectionNotFound
from .chat_events import clarification_event, done_event, sse
from .chat_service import ChatService

logger = logging.getLogger("text2sql.chat")

KEEPALIVE_SECONDS = 10
INTERNAL_ERROR = "Lỗi không mong muốn khi xử lý câu hỏi."

ChatServiceFactory = Callable[[], AbstractContextManager[ChatService]]
Disconnected = Callable[[], Awaitable[bool]]

READY = object()
END = object()


def error_payload(error: Exception) -> dict[str, Any]:
    if isinstance(error, AppError):
        return {"code": error.code, "message": str(error)}
    return {"code": "internal_error", "message": INTERNAL_ERROR}


class ChatStream:
    def __init__(self, factory: ChatServiceFactory, body: ChatIn, disconnected: Disconnected | None = None) -> None:
        self.factory = factory
        self.body = body
        self.disconnected = disconnected
        self.stopped = threading.Event()
        self.queue: asyncio.Queue[Any] = asyncio.Queue()
        self.loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        threading.Thread(target=self._work, name="text2sql-chat", daemon=True).start()
        first = await self.queue.get()
        if isinstance(first, Exception):
            raise first

    async def events(self) -> AsyncIterator[str]:
        try:
            while True:
                try:
                    item = await asyncio.wait_for(self.queue.get(), KEEPALIVE_SECONDS)
                except TimeoutError:
                    if self.disconnected is not None and await self.disconnected():
                        return
                    yield ": keep-alive\n\n"
                    continue
                if item is END:
                    return
                yield item
        finally:
            self.stopped.set()

    def _work(self) -> None:
        ready = False
        # A new thread starts with an empty context, so the token is set here, not in the route.
        SCOPE_TOKEN.set(str(self.body.scope_token) if self.body.scope_token else None)
        try:
            with self.factory() as service:
                body = self.body
                if service.session.get(DatabaseConnection, body.connection_id) is None:
                    raise Text2SqlConnectionNotFound()
                prepared = service.prepare(
                    body.connection_id, body.question, body.chat_history, body.user_id, body.conversation_id,
                    body.resume_id,
                )
                ready = True
                self._put(READY)
                out = service.execute(prepared, self._emit, self.stopped.is_set)
                if out.status == "needs_clarification":
                    self._put(sse("clarification", clarification_event(out)))
                self._put(sse("done", done_event(out)))
        except Exception as error:
            if not ready:
                self._put(error)
                return
            if isinstance(error, Text2SqlClientDisconnected):
                logger.info("Client ngắt kết nối giữa lượt chat")
            elif not isinstance(error, AppError):
                logger.exception("Lượt chat lỗi")
            self._put(sse("error", error_payload(error)))
        finally:
            if ready:
                self._put(END)

    def _emit(self, event: str, data: dict[str, Any]) -> None:
        if self.stopped.is_set():
            raise Text2SqlClientDisconnected()
        self._put(sse(event, data))

    def _put(self, item: Any) -> None:
        try:
            self.loop.call_soon_threadsafe(self.queue.put_nowait, item)
        except RuntimeError:
            self.stopped.set()
