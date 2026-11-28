import unittest

from pydantic import SecretStr

from backend.core.setting import config

SERVICE_KEY = "test-service-key-" + "k" * 32
SERVICE_HEADERS = {"X-Service-Key": SERVICE_KEY}


def use_service_key(case: unittest.TestCase) -> dict[str, str]:
    case.addCleanup(setattr, config, "text2sql_service_key", config.text2sql_service_key)
    config.text2sql_service_key = SecretStr(SERVICE_KEY)
    return SERVICE_HEADERS
