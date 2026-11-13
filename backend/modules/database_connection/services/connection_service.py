from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.core.setting import config
from backend.modules.database_connection.utils.exceptions import (
    ConnectionAlreadyExistsError,
    ConnectionNotFoundError,
    InvalidConnectionError,
    SourceDatabaseUnavailableError,
)
from backend.modules.database_connection.models import DatabaseConnection
from backend.modules.database_connection.repositories import DatabaseConnectionRepository


@dataclass(frozen=True)
class ConnectionSummary:
    id: UUID
    name: str
    dialect: str
    driver: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


def probe_source_database(url: URL) -> None:
    engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 5})
    try:
        with engine.connect():
            pass
    finally:
        engine.dispose()


class ConnectionService:
    def __init__(
        self,
        session: Session,
        *,
        encryption_key: str | None = None,
        probe: Callable[[URL], None] = probe_source_database,
    ) -> None:
        key = encryption_key if encryption_key is not None else config.require_connection_encryption_key()
        self.cipher = Fernet(key.encode())
        self.session = session
        self.repository = DatabaseConnectionRepository(session)
        self.probe = probe

    def test_connection(self, uri: str) -> tuple[str, str]:
        url = self._parse_url(uri)
        self._probe(url)
        return "postgresql", "psycopg"

    def register(self, *, name: str, uri: str) -> ConnectionSummary:
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 255:
            raise InvalidConnectionError()
        if self.repository.read_by_name(clean_name) is not None:
            raise ConnectionAlreadyExistsError()

        url = self._parse_url(uri)
        self._probe(url)
        ciphertext = self.cipher.encrypt(uri.encode("utf-8")).decode("ascii")
        entity = DatabaseConnection(
            name=clean_name,
            dialect="postgresql",
            driver="psycopg",
            uri_ciphertext=ciphertext,
            is_active=True,
        )
        try:
            self.repository.create(entity)
        except IntegrityError:
            raise ConnectionAlreadyExistsError() from None
        return self._summary(entity)

    def list_connections(self, *, offset: int = 0, limit: int = 100) -> list[ConnectionSummary]:
        return [self._summary(entity) for entity in self.repository.read_all(offset=offset, limit=limit)]

    def get_connection(self, connection_id: UUID) -> ConnectionSummary:
        entity = self.repository.read_by_id(connection_id)
        if entity is None:
            raise ConnectionNotFoundError()
        return self._summary(entity)

    def update(self, connection_id: UUID, changes: dict[str, Any]) -> ConnectionSummary:
        entity = self.repository.read_by_id(connection_id)
        if entity is None:
            raise ConnectionNotFoundError()
        values: dict[str, Any] = {}
        if "name" in changes:
            name = changes["name"]
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 255:
                raise InvalidConnectionError()
            clean_name = name.strip()
            existing = self.repository.read_by_name(clean_name)
            if existing is not None and existing.id != connection_id:
                raise ConnectionAlreadyExistsError()
            values["name"] = clean_name
        if "is_active" in changes:
            active = changes["is_active"]
            if not isinstance(active, bool):
                raise InvalidConnectionError()
            values["is_active"] = active
        if "uri" in changes:
            uri = changes["uri"]
            if not isinstance(uri, str):
                raise InvalidConnectionError()
            url = self._parse_url(uri)
            self._probe(url)
            values["uri_ciphertext"] = self.cipher.encrypt(uri.encode("utf-8")).decode("ascii")
            values["dialect"] = "postgresql"
            values["driver"] = "psycopg"
        if not values:
            raise InvalidConnectionError()
        try:
            self.repository.update(entity, values)
        except IntegrityError:
            raise ConnectionAlreadyExistsError() from None
        return self._summary(entity)

    def delete(self, connection_id: UUID) -> None:
        if not self.repository.delete_by_id(connection_id):
            raise ConnectionNotFoundError()

    def _parse_url(self, uri: str) -> URL:
        if not uri or not uri.strip():
            raise InvalidConnectionError()
        try:
            url = make_url(uri)
        except (ArgumentError, ValueError, TypeError):
            raise InvalidConnectionError() from None
        if url.drivername != "postgresql+psycopg" or not url.host or not url.database:
            raise InvalidConnectionError()
        try:
            port = url.port
        except ValueError:
            raise InvalidConnectionError() from None
        if port is not None and not 1 <= port <= 65535:
            raise InvalidConnectionError()
        return url

    def _probe(self, url: URL) -> None:
        try:
            self.probe(url)
        except (SQLAlchemyError, OSError, TimeoutError):
            raise SourceDatabaseUnavailableError() from None

    @staticmethod
    def _summary(entity: DatabaseConnection) -> ConnectionSummary:
        return ConnectionSummary(
            id=entity.id,
            name=entity.name,
            dialect=entity.dialect,
            driver=entity.driver,
            is_active=entity.is_active,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
