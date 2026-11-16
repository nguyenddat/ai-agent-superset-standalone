from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from ..chat.events import ChatEvent
from ..chat.pipeline import ChatPipeline

router = APIRouter()

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
QuestionText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection_id: UUID
    question: QuestionText | None = None
    user_id: str | None = Field(default=None, max_length=255)
    conversation_id: UUID | None = None
    previous_turn_id: UUID | None = None
    join_signature: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("user_id")
    @classmethod
    def _blank_user(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @model_validator(mode="after")
    def _turn_fields(self) -> "ChatIn":
        if self.conversation_id is not None and self.user_id is None:
            raise ValueError("conversation_id cần đi cùng user_id.")
        if (self.previous_turn_id is None) != (self.join_signature is None):
            raise ValueError("previous_turn_id và join_signature phải gửi cùng nhau.")
        if self.previous_turn_id is not None and self.conversation_id is None:
            raise ValueError("Tiếp tục một lượt cần conversation_id.")
        if self.question is None and self.previous_turn_id is None:
            raise ValueError("Thiếu câu hỏi.")
        return self


def get_chat_pipeline() -> ChatPipeline:
    return ChatPipeline()


def _sse(events: Iterator[ChatEvent]) -> Iterator[str]:
    try:
        for event in events:
            yield event.to_sse()
    finally:
        closer = getattr(events, "close", None)
        if closer is not None:
            closer()


@router.post("/chat", response_class=StreamingResponse)
def chat(body: ChatIn, pipeline: Annotated[ChatPipeline, Depends(get_chat_pipeline)]) -> StreamingResponse:
    pipeline.check(body.connection_id)
    turn_request = None
    if body.user_id is not None:
        turn_request = pipeline.prepare_turn(
            body.connection_id, body.user_id, body.conversation_id, body.previous_turn_id, body.join_signature,
        )
    question = body.question
    if question is None:
        question = turn_request.resume.question if turn_request and turn_request.resume else ""
    return StreamingResponse(
        _sse(pipeline.run(body.connection_id, question, body.user_id, turn_request=turn_request)),
        media_type="text/event-stream", headers=SSE_HEADERS,
    )
