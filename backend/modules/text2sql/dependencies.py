from collections.abc import Generator, Iterator
from contextlib import ExitStack, contextmanager
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.agent_package.get_embedding_models import OpenRouterEmbedding
from backend.core.database import get_database, get_session_factory

from .repositories import QdrantRepository
from .services import ChatService
from .services.chat_stream import ChatServiceFactory

IndexServices = tuple[QdrantRepository, OpenRouterEmbedding, Session]


def get_index_services(session: Annotated[Session, Depends(get_database)]) -> Generator[IndexServices]:
    index = QdrantRepository()
    embedding = OpenRouterEmbedding()
    try:
        yield index, embedding, session
    finally:
        index.close()
        embedding.close()


def get_chat_service(services: Annotated[IndexServices, Depends(get_index_services)]) -> ChatService:
    index, embedding, session = services
    return ChatService(session, index, embedding)


@contextmanager
def open_chat_service() -> Iterator[ChatService]:
    with ExitStack() as stack:
        session = get_session_factory()()
        stack.callback(session.close)
        index = QdrantRepository()
        stack.callback(index.close)
        embedding = OpenRouterEmbedding()
        stack.callback(embedding.close)
        try:
            yield ChatService(session, index, embedding)
        except Exception:
            session.rollback()
            raise


def get_chat_service_factory() -> ChatServiceFactory:
    return open_chat_service
