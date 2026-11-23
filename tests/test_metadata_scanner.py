import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy.engine import make_url

from backend.modules.database_connection.services.metadata_service import scan_source_database


class MetadataScannerTests(unittest.TestCase):
    def test_only_reflects_tables_with_select_and_schema_usage(self) -> None:
        engine = MagicMock()
        connection = engine.connect.return_value.__enter__.return_value
        connection.execute.return_value = [("public", "orders"), ("public", "order_view")]
        inspector = MagicMock()
        inspector.get_schema_names.return_value = ["public", "private"]
        inspector.get_table_names.side_effect = lambda schema: (
            ["orders", "secret"] if schema == "public" else ["hidden"]
        )
        inspector.get_view_names.side_effect = lambda schema: ["order_view"] if schema == "public" else []
        inspector.get_materialized_view_names.return_value = []
        inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
        inspector.get_columns.return_value = [{"name": "id", "type": "INTEGER"}]
        inspector.get_table_comment.return_value = {"text": None}

        with (
            patch("backend.modules.database_connection.services.metadata_service.create_engine", return_value=engine),
            patch("backend.modules.database_connection.services.metadata_service.inspect", return_value=inspector),
        ):
            schemas = scan_source_database(make_url("postgresql+psycopg://reader@example.test/source"))

        self.assertEqual([schema.name for schema in schemas], ["public"])
        self.assertEqual([table.name for table in schemas[0].tables], ["order_view", "orders"])
        self.assertEqual(inspector.get_columns.call_count, 2)
        sql = str(connection.execute.call_args.args[0])
        self.assertIn("has_table_privilege(current_user, c.oid, 'SELECT')", sql)
        self.assertIn("has_schema_privilege(current_user, n.oid, 'USAGE')", sql)
        engine.dispose.assert_called_once()

    def test_no_readable_tables_does_not_reflect_columns(self) -> None:
        engine = MagicMock()
        connection = engine.connect.return_value.__enter__.return_value
        connection.execute.return_value = []
        inspector = MagicMock()
        inspector.get_schema_names.return_value = ["public"]

        with (
            patch("backend.modules.database_connection.services.metadata_service.create_engine", return_value=engine),
            patch("backend.modules.database_connection.services.metadata_service.inspect", return_value=inspector),
        ):
            schemas = scan_source_database(make_url("postgresql+psycopg://reader@example.test/source"))

        self.assertEqual(schemas, [])
        inspector.get_table_names.assert_not_called()
        inspector.get_columns.assert_not_called()
        engine.dispose.assert_called_once()


if __name__ == "__main__":
    unittest.main()
