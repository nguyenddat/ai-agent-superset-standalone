from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.core.database import get_database

from .services import DataDictionaryAutofillService, DataDictionaryService


def get_data_dictionary_service(session: Annotated[Session, Depends(get_database)]) -> DataDictionaryService:
    return DataDictionaryService(session)


def get_data_dictionary_autofill_service(
    session: Annotated[Session, Depends(get_database)],
) -> DataDictionaryAutofillService:
    return DataDictionaryAutofillService(session)
