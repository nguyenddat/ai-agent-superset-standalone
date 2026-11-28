import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.common.base_exceptions import AppError
from backend.core.security import require_service_key
from backend.core.setting import config
from backend.modules.business_model.routes.router_business_model import (
    router as business_model_router,
)
from backend.modules.conversation.routes.router_conversation import (
    router as conversation_router,
)
from backend.modules.data_dictionary.routes.router_data_dictionary import (
    router as data_dictionary_router,
)
from backend.modules.data_lineage.routes.router_data_lineage import (
    router as data_lineage_router,
)
from backend.modules.database_connection.routes.router_database_connection import (
    router as database_connection_router,
)
from backend.modules.database_connection.routes.router_database_metadata import (
    router as database_metadata_router,
)
from backend.modules.expert_rule_management.routes.router_expert_rule import (
    router as expert_rule_router,
)
from backend.modules.glossary_management.routes.router_glossary import (
    router as glossary_router,
)
from backend.modules.metric_management.routes.router_metric import (
    router as metric_router,
)
from backend.modules.own_knowledge.routes.router_own_knowledge import (
    router as own_knowledge_router,
)
from backend.modules.text2sql.routes import router as text2sql_router
from backend.modules.text2sql.services import register_triggers, warm_up_masker

register_triggers()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    threading.Thread(target=warm_up_masker, name="pii-warm-up", daemon=True).start()
    yield


app = FastAPI(title="AI Agent Superset Standalone API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
SERVICE_ONLY = [Depends(require_service_key)]  # own-knowledge keeps its own agent/admin keys
app.include_router(database_connection_router, dependencies=SERVICE_ONLY)
app.include_router(database_metadata_router, dependencies=SERVICE_ONLY)
app.include_router(data_dictionary_router, dependencies=SERVICE_ONLY)
app.include_router(business_model_router, dependencies=SERVICE_ONLY)
app.include_router(data_lineage_router, dependencies=SERVICE_ONLY)
app.include_router(metric_router, dependencies=SERVICE_ONLY)
app.include_router(glossary_router, dependencies=SERVICE_ONLY)
app.include_router(expert_rule_router, dependencies=SERVICE_ONLY)
app.include_router(own_knowledge_router)
app.include_router(text2sql_router, dependencies=SERVICE_ONLY)
app.include_router(conversation_router, dependencies=SERVICE_ONLY)


@app.exception_handler(AppError)
def handle_app_error(_request: Request, error: AppError) -> JSONResponse:
    return JSONResponse(status_code=error.status, content={"detail": str(error)})


@app.exception_handler(RequestValidationError)
def handle_validation_error(_request: Request, _error: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "Dữ liệu yêu cầu không hợp lệ."})


@app.exception_handler(HTTPException)
def handle_http_error(_request: Request, error: HTTPException) -> JSONResponse:
    detail = error.detail if isinstance(error.detail, str) else "Yêu cầu không hợp lệ."
    return JSONResponse(status_code=error.status_code, content={"detail": detail})


@app.exception_handler(Exception)
def handle_unexpected_error(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "Đã xảy ra lỗi hệ thống."})
