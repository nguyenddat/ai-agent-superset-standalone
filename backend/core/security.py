import hmac
from typing import Annotated

from fastapi import Header, HTTPException

from backend.core.setting import config


def require_service_key(x_service_key: Annotated[str | None, Header()] = None) -> None:
    expected = config.text2sql_service_key
    if expected is None or not expected.get_secret_value():  # fail closed; compose passes "" when unset
        raise HTTPException(status_code=503, detail="Backend chưa được cấu hình TEXT2SQL_SERVICE_KEY.")
    if x_service_key is None or not hmac.compare_digest(x_service_key, expected.get_secret_value()):
        raise HTTPException(status_code=401, detail="Thiếu hoặc sai X-Service-Key.")
