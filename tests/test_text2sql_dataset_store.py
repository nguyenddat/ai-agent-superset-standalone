import unittest
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.modules.database_connection.models import (
    DatabaseColumn,
    DatabaseConnection,
    DatabaseSchema,
    DatabaseTable,
)
from backend.modules.model_registry import register_all_models
from backend.modules.text2sql.common.errors import Text2SqlEntityNotFound, Text2SqlInvalidRequest
from backend.modules.text2sql.dataset.join_schemas import JoinOption
from backend.modules.text2sql.dataset.store import DatasetStore
from backend.modules.text2sql.models import QueryDataset

register_all_models()


class DatasetStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        self.store = DatasetStore(self.session)
        self.connection, self.tables, self.columns = self.build_catalog("orders", "customers", "weather")
        self.option = self.join_option(self.connection, "orders", ["orders", "customers"], signature="a" * 64)

    def build_catalog(self, *table_names: str):
        s = self.session
        connection = DatabaseConnection(name=f"c-{uuid4()}", dialect="postgresql", uri_ciphertext="x")
        s.add(connection)
        s.flush()
        schema = DatabaseSchema(connection_id=connection.id, name="public")
        s.add(schema)
        s.flush()
        tables, columns = {}, {}
        for table_name in table_names:
            table = DatabaseTable(schema_id=schema.id, name=table_name, table_type="TABLE")
            s.add(table)
            s.flush()
            tables[table_name] = table
            for position, column_name in enumerate(["id", "name", "value"], start=1):
                column = DatabaseColumn(
                    table_id=table.id, name=column_name, data_type="text", ordinal_position=position, is_nullable=True,
                )
                s.add(column)
                s.flush()
                columns[f"{table_name}.{column_name}"] = column
        return connection, tables, columns

    def join_option(self, connection, root: str, table_names: list[str], signature: str) -> JoinOption:
        tables = self.tables if connection is self.connection else self.other_tables
        root_table = tables[root]
        return JoinOption(
            signature=signature,
            root_table_id=root_table.id,
            from_sql=f'FROM "public"."{root}" AS "t1"',
            steps=[],
            edge_ids=[uuid4()],
            table_ids=[tables[name].id for name in table_names],
            aliases={"t1": root},
            warnings=[],
        )

    def column_ids(self, *keys: str) -> list[UUID]:
        return [self.columns[key].id for key in keys]

    def test_creates_dataset_from_join_option(self) -> None:
        dataset, created = self.store.get_or_create(self.connection.id, self.option)
        self.assertTrue(created)
        self.assertEqual(dataset.connection_id, self.connection.id)
        self.assertEqual(dataset.signature, self.option.signature)
        self.assertEqual(dataset.root_table_id, self.tables["orders"].id)
        self.assertEqual(dataset.table_ids, [str(table_id) for table_id in self.option.table_ids])
        self.assertEqual(dataset.edge_ids, [str(edge_id) for edge_id in self.option.edge_ids])
        self.assertEqual(dataset.from_sql, self.option.from_sql)
        self.assertEqual(dataset.selected_column_ids, [])

    def test_reuses_dataset_with_same_signature_and_root(self) -> None:
        first, _ = self.store.get_or_create(self.connection.id, self.option)
        second, created = self.store.get_or_create(self.connection.id, self.option)
        self.assertFalse(created)
        self.assertEqual(first.id, second.id)
        count = len(self.session.scalars(select(QueryDataset)).all())
        self.assertEqual(count, 1)

    def test_different_root_creates_separate_dataset(self) -> None:
        first, _ = self.store.get_or_create(self.connection.id, self.option)
        other_root = self.join_option(self.connection, "customers", ["orders", "customers"], signature="a" * 64)
        second, created = self.store.get_or_create(self.connection.id, other_root)
        self.assertTrue(created)
        self.assertNotEqual(first.id, second.id)

    def test_concurrent_insert_falls_back_to_existing_row(self) -> None:
        winner, _ = self.store.get_or_create(self.connection.id, self.option)
        original_find = self.store._find
        calls = []

        def find_missing_once(*args):
            calls.append(args)
            return None if len(calls) == 1 else original_find(*args)

        self.store._find = find_missing_once
        dataset, created = self.store.get_or_create(self.connection.id, self.option)
        self.assertFalse(created)
        self.assertEqual(dataset.id, winner.id)
        self.assertEqual(len(self.session.scalars(select(QueryDataset)).all()), 1)

    def test_add_columns_is_append_only_deduplicated_and_ordered(self) -> None:
        dataset, _ = self.store.get_or_create(self.connection.id, self.option)
        added = self.store.add_columns(dataset, self.column_ids("orders.value", "customers.name", "orders.value"))
        self.assertEqual(added.added, self.column_ids("orders.value", "customers.name"))
        self.assertIsNone(added.warning)
        added = self.store.add_columns(dataset, self.column_ids("customers.name", "orders.id"))
        self.assertEqual(added.added, self.column_ids("orders.id"))
        self.assertEqual(self.store.add_columns(dataset, self.column_ids("orders.id")).added, [])
        self.session.expire_all()
        reloaded = self.store.get(self.connection.id, dataset.id)
        expected = [str(column_id) for column_id in self.column_ids("orders.value", "customers.name", "orders.id")]
        self.assertEqual(reloaded.selected_column_ids, expected)

    def test_rejects_column_outside_dataset_tables(self) -> None:
        dataset, _ = self.store.get_or_create(self.connection.id, self.option)
        with self.assertRaises(Text2SqlInvalidRequest) as context:
            self.store.add_columns(dataset, self.column_ids("orders.name", "weather.value"))
        self.assertIn(str(self.columns["weather.value"].id), str(context.exception))
        with self.assertRaises(Text2SqlInvalidRequest):
            self.store.add_columns(dataset, [uuid4()])
        self.assertEqual(dataset.selected_column_ids, [])

    def test_column_limit_skips_new_columns_with_a_warning(self) -> None:
        dataset, _ = self.store.get_or_create(self.connection.id, self.option)
        table = self.tables["orders"]
        extra = []
        for position in range(4, 206):
            column = DatabaseColumn(
                table_id=table.id, name=f"c{position}", data_type="text", ordinal_position=position, is_nullable=True,
            )
            self.session.add(column)
            extra.append(column)
        self.session.flush()
        self.assertEqual(len(self.store.add_columns(dataset, [column.id for column in extra[:200]]).added), 200)
        skipped = self.store.add_columns(dataset, [extra[200].id, extra[0].id])
        self.assertEqual(skipped.added, [])
        self.assertIn("200", skipped.warning)
        self.assertEqual(self.store.add_columns(dataset, [extra[0].id]).warning, None)
        with self.assertRaises(Text2SqlInvalidRequest):
            self.store.add_columns(dataset, self.column_ids("weather.value"))
        self.session.expire_all()
        self.assertEqual(len(self.store.get(self.connection.id, dataset.id).selected_column_ids), 200)

    def test_other_connection_cannot_see_dataset(self) -> None:
        dataset, _ = self.store.get_or_create(self.connection.id, self.option)
        other_connection, self.other_tables, _ = self.build_catalog("orders", "customers")
        with self.assertRaises(Text2SqlEntityNotFound):
            self.store.get(other_connection.id, dataset.id)
        self.assertEqual(self.store.list(other_connection.id), [])
        self.assertEqual([item.id for item in self.store.list(self.connection.id)], [dataset.id])
        other_option = self.join_option(other_connection, "orders", ["orders", "customers"], signature="a" * 64)
        other_dataset, created = self.store.get_or_create(other_connection.id, other_option)
        self.assertTrue(created)
        self.assertNotEqual(other_dataset.id, dataset.id)

    def test_list_respects_limit(self) -> None:
        self.store.get_or_create(self.connection.id, self.option)
        self.store.get_or_create(
            self.connection.id, self.join_option(self.connection, "customers", ["customers"], signature="b" * 64)
        )
        self.assertEqual(len(self.store.list(self.connection.id, limit=1)), 1)
        self.assertEqual(len(self.store.list(self.connection.id)), 2)

    def test_deleting_connection_or_root_table_cascades(self) -> None:
        foreign_keys = {key.parent.name: key for key in QueryDataset.__table__.foreign_keys}
        self.assertEqual(foreign_keys["connection_id"].column.table.name, "database_connections")
        self.assertEqual(foreign_keys["connection_id"].ondelete, "CASCADE")
        self.assertEqual(foreign_keys["root_table_id"].column.table.name, "database_tables")
        self.assertEqual(foreign_keys["root_table_id"].ondelete, "CASCADE")


if __name__ == "__main__":
    unittest.main()
