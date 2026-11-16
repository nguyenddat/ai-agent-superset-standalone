from fastapi import APIRouter

from . import chat, ingestion, suggestions

router = APIRouter(prefix="/api/v1/text2sql", tags=["text2sql"])
router.include_router(ingestion.router)
router.include_router(chat.router)
router.include_router(suggestions.router)
