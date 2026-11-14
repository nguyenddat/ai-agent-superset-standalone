from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.common.base_exceptions import AppError
from backend.core.setting import config
from backend.modules.business_model.routes.router_business_model import (
    router as business_model_router,
)
from backend.modules.data_lineage.routes.router_data_lineage import router as data_lineage_router
from backend.modules.metric_management.routes.router_metric import router as metric_router
from backend.modules.data_dictionary.routes.router_data_dictionary import (
    router as data_dictionary_router,
)
from backend.modules.database_connection.routes.router_database_connection import (
    router as database_connection_router,
)
from backend.modules.database_connection.routes.router_database_metadata import (
    router as database_metadata_router,
)

app = FastAPI(title="AI Agent Superset Standalone API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.frontend_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(database_connection_router)
app.include_router(database_metadata_router)
app.include_router(data_dictionary_router)
app.include_router(business_model_router)
app.include_router(data_lineage_router)
app.include_router(metric_router)


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
