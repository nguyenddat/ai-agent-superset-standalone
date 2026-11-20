from fastapi import APIRouter

from . import router_chart, router_chat, router_ingestion

router = APIRouter(prefix="/api/v1/text2sql", tags=["text2sql"])
router.include_router(router_ingestion.router)
router.include_router(router_chat.router)
router.include_router(router_chart.router)

__all__ = ["router"]
