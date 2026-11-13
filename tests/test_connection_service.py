import unittest
from uuid import uuid7

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.common.base_model import Base
from backend.modules.database_connection.utils.exceptions import (
    ConnectionAlreadyExistsError,
    ConnectionNotFoundError,
    InvalidConnectionError,
    SourceDatabaseUnavailableError,
)
from backend.modules.database_connection.models import DatabaseConnection
from backend.modules.database_connection.services import ConnectionService


SOURCE_URI = "postgresql+psycopg://reader:secret@db.example.test:5432/source"


class ConnectionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.key = Fernet.generate_key()
        self.probed = []
        self.service = ConnectionService(
            self.session,
            encryption_key=self.key.decode(),
            probe=self.probed.append,
        )

    def tearDown(self) -> None:
        self.session.rollback()
        self.session.close()
        self.engine.dispose()

    def test_register_encrypts_uri_and_returns_only_safe_fields(self) -> None:
        summary = self.service.register(name="  Analytics  ", uri=SOURCE_URI)
        entity = self.session.scalar(select(DatabaseConnection))

        self.assertEqual(summary.name, "Analytics")
        self.assertEqual(summary.id.version, 7)
        self.assertEqual(summary.dialect, "postgresql")
        self.assertEqual(summary.driver, "psycopg")
        self.assertNotIn("uri", vars(summary))
        self.assertNotIn("secret", entity.uri_ciphertext)
        self.assertEqual(Fernet(self.key).decrypt(entity.uri_ciphertext.encode()).decode(), SOURCE_URI)
        self.assertEqual(len(self.probed), 1)
        self.assertEqual(self.service.get_connection(summary.id).id, summary.id)
        self.assertEqual([item.id for item in self.service.list_connections()], [summary.id])
        self.assertTrue(self.session.in_transaction())

    def test_duplicate_name_is_rejected_before_probe(self) -> None:
        self.service.register(name="Analytics", uri=SOURCE_URI)
        with self.assertRaises(ConnectionAlreadyExistsError):
            self.service.register(name="Analytics", uri=SOURCE_URI)
        self.assertEqual(len(self.probed), 1)

    def test_invalid_url_and_name_do_not_create_rows(self) -> None:
        with self.assertRaises(InvalidConnectionError):
            self.service.register(name=" ", uri=SOURCE_URI)
        with self.assertRaises(InvalidConnectionError):
            self.service.register(name="Invalid", uri="sqlite:///tmp/example.db")
        self.assertEqual(self.service.list_connections(), [])

    def test_probe_failure_uses_safe_error(self) -> None:
        def unavailable(_url):
            raise OSError("secret connection detail")

        service = ConnectionService(self.session, encryption_key=self.key.decode(), probe=unavailable)
        with self.assertRaises(SourceDatabaseUnavailableError) as error:
            service.register(name="Unavailable", uri=SOURCE_URI)
        self.assertNotIn("secret", str(error.exception))
        self.assertEqual(self.service.list_connections(), [])

    def test_missing_connection(self) -> None:
        with self.assertRaises(ConnectionNotFoundError):
            self.service.get_connection(uuid7())


if __name__ == "__main__":
    unittest.main()
