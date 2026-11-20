from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models.chat_checkpoint import ChatCheckpoint


class ChatCheckpointRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def locked(self, checkpoint_id: UUID, now: datetime) -> ChatCheckpoint | None:
        return self.session.scalar(
            select(ChatCheckpoint)
            .where(ChatCheckpoint.id == checkpoint_id, ChatCheckpoint.expires_at > now)
            .with_for_update()
        )

    def add(self, checkpoint: ChatCheckpoint) -> None:
        self.session.add(checkpoint)
        self.session.flush()

    def remove(self, checkpoint: ChatCheckpoint) -> None:
        self.session.delete(checkpoint)
        self.session.flush()

    def purge_expired(self, now: datetime) -> int:
        result = self.session.execute(delete(ChatCheckpoint).where(ChatCheckpoint.expires_at <= now))
        return result.rowcount or 0
