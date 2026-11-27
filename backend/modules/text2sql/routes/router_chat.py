import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.core.database import get_database
from backend.core.setting import config
from backend.modules.database_connection.models import DatabaseConnection

from ..dependencies import get_chat_service, get_chat_service_factory
from ..repositories.source_query_repository import SCOPE_TOKEN
from ..schemas import ChatIn, ChatOut
from ..services import ChatService
from ..services.chat_stream import ChatServiceFactory, ChatStream
from ..utils.exceptions import Text2SqlConnectionNotFound


def require_service_key(x_service_key: Annotated[str | None, Header()] = None) -> None:
    expected = config.text2sql_service_key
    if expected is None or not expected.get_secret_value():  # unset (compose passes "")
        return
    if x_service_key is None or not hmac.compare_digest(x_service_key, expected.get_secret_value()):
        raise HTTPException(status_code=401, detail="Thiếu hoặc sai X-Service-Key.")


router = APIRouter(dependencies=[Depends(require_service_key)])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

SessionDep = Annotated[Session, Depends(get_database)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
ChatServiceFactoryDep = Annotated[ChatServiceFactory, Depends(get_chat_service_factory)]


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn, session: SessionDep, chat_service: ChatServiceDep) -> ChatOut:
    if session.get(DatabaseConnection, body.connection_id) is None:
        raise Text2SqlConnectionNotFound()
    # Sync route: runs in a worker thread with its own copy of the context, so nothing leaks.
    SCOPE_TOKEN.set(str(body.scope_token) if body.scope_token else None)
    return chat_service.chat(
        body.connection_id, body.question, body.chat_history, body.user_id, body.conversation_id, body.resume_id,
    )


@router.post("/chat/stream", response_class=StreamingResponse)
async def chat_stream(body: ChatIn, request: Request, factory: ChatServiceFactoryDep) -> StreamingResponse:
    stream = ChatStream(factory, body, request.is_disconnected)
    await stream.start()
    return StreamingResponse(stream.events(), media_type="text/event-stream", headers=SSE_HEADERS)
