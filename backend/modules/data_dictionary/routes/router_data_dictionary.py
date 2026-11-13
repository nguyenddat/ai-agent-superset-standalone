import json
import logging
from collections.abc import Iterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from backend.common.base_exceptions import AppError

from ..dependencies import (
    get_data_dictionary_autofill_service,
    get_data_dictionary_service,
)
from ..schemas.schema_data_dictionary import (
    ColumnDictionariesIn,
    TableDictionaryIn,
    TableDictionaryOut,
)
from ..services import DataDictionaryAutofillService, DataDictionaryService
from ..services.autofill_service import AutofillPlan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["data-dictionary"])
DataDictionaryServiceDep = Annotated[DataDictionaryService, Depends(get_data_dictionary_service)]
AutofillServiceDep = Annotated[DataDictionaryAutofillService, Depends(get_data_dictionary_autofill_service)]


@router.get("/tables/{table_id}/dictionary", response_model=TableDictionaryOut)
def get_table_dictionary(table_id: UUID, service: DataDictionaryServiceDep) -> TableDictionaryOut:
    return TableDictionaryOut.model_validate(service.get_table_dictionary(table_id))


@router.put("/tables/{table_id}/dictionary", response_model=TableDictionaryOut)
def save_table_dictionary(
    table_id: UUID, body: TableDictionaryIn, service: DataDictionaryServiceDep,
) -> TableDictionaryOut:
    response = TableDictionaryOut.model_validate(service.save_table_dictionary(table_id, body.model_dump()))
    service.session.commit()
    return response


@router.put("/tables/{table_id}/dictionary/columns", response_model=TableDictionaryOut)
def save_column_dictionaries(
    table_id: UUID, body: ColumnDictionariesIn, service: DataDictionaryServiceDep,
) -> TableDictionaryOut:
    items = [item.model_dump() for item in body.columns]
    response = TableDictionaryOut.model_validate(service.save_column_dictionaries(table_id, items))
    service.session.commit()
    return response


@router.post("/tables/{table_id}/dictionary/autofill")
def autofill_table_dictionary(table_id: UUID, service: AutofillServiceDep) -> StreamingResponse:
    plan = service.prepare(table_id)
    return StreamingResponse(
        _autofill_stream(service, plan),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(jsonable_encoder(data), ensure_ascii=False)}\n\n"


def _autofill_stream(service: DataDictionaryAutofillService, plan: AutofillPlan) -> Iterator[str]:
    try:
        for event in service.events(plan):
            service.session.commit()
            yield _sse(event.name, event.data)
    except AppError as error:
        service.session.rollback()
        yield _sse("error", {"code": error.code, "message": str(error)})
    except Exception:
        service.session.rollback()
        logger.exception("Data dictionary autofill failed (table_id=%s)", plan.table_id)
        yield _sse("error", {"code": "dictionary_autofill_failed", "message": "Không thể tạo gợi ý từ điển dữ liệu."})
    finally:
        service.release(plan)
