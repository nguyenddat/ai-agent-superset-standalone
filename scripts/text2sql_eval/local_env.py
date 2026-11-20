import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import SecretStr
from sqlalchemy.engine import URL, make_url

from backend.core.setting import config


def override_app_db(address: str) -> None:
    if not address:
        return
    host, _, port = address.partition(":")
    url = make_url(config.require_database_url()).set(host=host, port=int(port) if port else None)
    config.database_url = SecretStr(url.render_as_string(hide_password=False))


def host_mapper(entries: list[str]) -> Any:
    mapping: dict[str, tuple[str, int | None]] = {}
    for entry in entries:
        source, _, target = entry.partition("=")
        host, _, port = target.partition(":")
        mapping[source.strip()] = (host.strip(), int(port) if port else None)

    def remap(url: URL) -> URL:
        target = mapping.get(url.host or "")
        return url.set(host=target[0], port=target[1]) if target else url

    return remap


def add_local_arguments(parser: Any) -> None:
    parser.add_argument("--app-db", default="", help="host:port thay cho host:port trong DATABASE_URL")
    parser.add_argument(
        "--source-host-map", action="append", default=[],
        help="host=host:port, đổi host của URI database nguồn khi chạy từ máy host (ví dụ tên service Compose)",
    )
