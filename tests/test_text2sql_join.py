import unittest
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.common.base_model import Base
from backend.modules.data_dictionary.models import ColumnDictionary, TableDictionary
from backend.modules.database_connection.models import (
    DatabaseColumn,
    DatabaseConnection,
    DatabaseSchema,
    DatabaseTable,
)
from backend.modules.model_registry import register_all_models
from backend.modules.text2sql.common.errors import Text2SqlInvalidRequest
from backend.modules.text2sql.dataset.field_service import FieldService
from backend.modules.text2sql.dataset.join_graph import JoinGraph
from backend.modules.text2sql.dataset.join_service import JoinService
from backend.modules.text2sql.vector_store.ingestion.documents.context import load_context
from backend.modules.text2sql.vector_store.retrieve.topic_search import TopicHit, TopicSearchOutcome

register_all_models()


class CatalogFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://", poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.session = Session(self.engine)
        self.addCleanup(self.session.close)
        s = self.session
        self.connection = DatabaseConnection(name=f"c-{uuid4()}", dialect="postgresql", uri_ciphertext="x")
        s.add(self.connection)
        s.flush()
        schema = DatabaseSchema(connection_id=self.connection.id, name="public")
        s.add(schema)
        s.flush()
        self.t, self.c = {}, {}
        layout = {
            "customers": ["id", "name"], "locations": ["id", "city"],
            "orders": ["id", "customer_id", "ship_from", "ship_to", "total"],
            "items": ["id", "order_id", "product_id", "qty"], "products": ["id", "title"], "weather": ["day", "temp"],
        }
        for table_name, columns in layout.items():
            table = DatabaseTable(schema_id=schema.id, name=table_name, table_type="TABLE")
            s.add(table)
            s.flush()
            self.t[table_name] = table
            s.add(TableDictionary(table_id=table.id, display_name=table_name.title()))
            for position, column_name in enumerate(columns, start=1):
                column = DatabaseColumn(
                    table_id=table.id, name=column_name, data_type="text", ordinal_position=position, is_nullable=True,
                )
                s.add(column)
                s.flush()
                self.c[f"{table_name}.{column_name}"] = column
        self.dictionaries = {}
        for key, column in self.c.items():
            dictionary = ColumnDictionary(
                column_id=column.id, display_name=key, is_primary_key=key.endswith(".id") or None,
            )
            s.add(dictionary)
            self.dictionaries[key] = dictionary
        s.flush()
        for child, parent in [
            ("orders.customer_id", "customers.id"), ("orders.ship_from", "locations.id"),
            ("orders.ship_to", "locations.id"), ("items.order_id", "orders.id"), ("items.product_id", "products.id"),
        ]:
            self.dictionaries[child].referenced_column_id = self.c[parent].id
        s.flush()

    def graph(self) -> JoinGraph:
        return JoinGraph(load_context(self.session, self.connection.id))

    def ids(self, *names):
        return [self.t[name].id for name in names]


class JoinGraphTests(CatalogFixture):
    def test_single_table_needs_no_join(self) -> None:
        plan = self.graph().plan(self.ids("orders"))
        self.assertEqual(plan.status, "ok")
        self.assertEqual(plan.options[0].steps, [])
        self.assertIn('"orders" AS t1', plan.options[0].from_sql)

    def test_declared_chain_joins_through_intermediate_tables(self) -> None:
        plan = self.graph().plan(self.ids("customers", "items"))
        self.assertEqual(plan.status, "ok")
        option = plan.options[0]
        self.assertEqual(set(option.aliases.values()), {"public.customers", "public.orders", "public.items"})
        self.assertEqual(len(option.steps), 2)
        self.assertEqual(option.from_sql.count("LEFT JOIN"), 2)
        self.assertIn('"customer_id"', option.from_sql)

    def test_the_root_is_the_table_that_does_not_multiply_rows(self) -> None:
        option = self.graph().plan(self.ids("customers", "items")).options[0]
        self.assertEqual(option.aliases["t1"], "public.items")
        self.assertEqual(option.warnings, [])

    def test_a_one_to_many_join_is_reported_as_row_multiplying(self) -> None:
        option = self.graph().plan(self.ids("customers", "orders")).options[0]
        self.assertEqual(option.aliases["t1"], "public.orders")
        two_children = self.graph().plan(self.ids("orders", "items", "customers")).options[0]
        self.assertEqual(two_children.aliases["t1"], "public.items")

    def test_fan_out_warning_appears_when_a_parent_must_lead(self) -> None:
        self.dictionaries["orders.customer_id"].referenced_column_id = None
        self.dictionaries["customers.id"].referenced_column_id = self.c["orders.customer_id"].id
        self.session.flush()
        option = self.graph().plan(self.ids("customers", "orders")).options[0]
        self.assertTrue(any("nhân số dòng" in text for text in option.warnings))
        self.assertTrue(any(step.multiplies_rows for step in option.steps))

    def test_the_root_follows_the_question_grain_when_given(self) -> None:
        graph = self.graph()
        customers_first = graph.plan(self.ids("customers", "orders"), root=self.t["customers"].id).options[0]
        self.assertEqual(customers_first.aliases["t1"], "public.customers")
        self.assertTrue(customers_first.steps[0].multiplies_rows)
        self.assertTrue(customers_first.warnings)
        orders_first = graph.plan(self.ids("customers", "orders"), root=self.t["orders"].id).options[0]
        self.assertEqual(orders_first.aliases["t1"], "public.orders")
        self.assertEqual(orders_first.warnings, [])

    def test_the_root_must_be_one_of_the_requested_tables(self) -> None:
        with self.assertRaises(Text2SqlInvalidRequest):
            self.graph().plan(self.ids("customers", "orders"), root=self.t["items"].id)

    def test_two_declared_relations_between_the_same_tables_are_ambiguous(self) -> None:
        plan = self.graph().plan(self.ids("orders", "locations"))
        self.assertEqual(plan.status, "ambiguous")
        self.assertEqual(len(plan.options), 2)
        self.assertEqual(len({option.signature for option in plan.options}), 2)

    def test_choosing_an_edge_resolves_the_ambiguity(self) -> None:
        graph = self.graph()
        choice = self.c["orders.ship_to"].id
        plan = graph.plan(self.ids("orders", "locations"), [choice])
        self.assertEqual(plan.status, "ok")
        self.assertEqual(plan.options[0].edge_ids, [choice])
        self.assertIn('"ship_to"', plan.options[0].from_sql)

    def test_undeclared_tables_are_reported_and_never_guessed(self) -> None:
        plan = self.graph().plan(self.ids("orders", "weather"))
        self.assertEqual(plan.status, "not_declared")
        self.assertEqual(plan.options, [])
        self.assertIn("public.weather", plan.message)
        self.assertIn("data dictionary", plan.message)

    def test_columns_with_the_same_name_are_not_joined_without_a_declaration(self) -> None:
        self.dictionaries["orders.customer_id"].referenced_column_id = None
        self.session.flush()
        self.assertEqual(self.graph().plan(self.ids("orders", "customers")).status, "not_declared")

    def test_signature_is_stable_regardless_of_table_order(self) -> None:
        first = self.graph().plan(self.ids("customers", "items")).options[0].signature
        second = self.graph().plan(self.ids("items", "customers")).options[0].signature
        third = self.graph().plan(self.ids("items", "products")).options[0].signature
        self.assertEqual(first, second)
        self.assertNotEqual(first, third)

    def test_sql_has_no_select_list_and_quotes_identifiers(self) -> None:
        option = self.graph().plan(self.ids("customers", "items")).options[0]
        self.assertTrue(option.from_sql.startswith("FROM "))
        self.assertNotIn("SELECT", option.from_sql.upper())

    def test_invalid_input_is_rejected(self) -> None:
        graph = self.graph()
        with self.assertRaises(Text2SqlInvalidRequest):
            graph.plan([uuid4()])
        with self.assertRaises(Text2SqlInvalidRequest):
            graph.plan([])
        with self.assertRaises(Text2SqlInvalidRequest):
            graph.plan(self.ids("orders"), [uuid4()])

    def test_service_rejects_an_unknown_connection(self) -> None:
        with self.assertRaises(Exception) as raised:
            JoinService(self.session).plan(uuid4(), self.ids("orders"))
        self.assertEqual(raised.exception.code, "text2sql_connection_not_found")


class FakeSearch:
    def __init__(self, outcome):
        self.outcome = outcome

    def search(self, connection_id, topic, question, k, reranker):
        return self.outcome


class FindFieldsTests(CatalogFixture):
    def hit(self, key, score, rerank):
        column = self.c[key]
        return TopicHit(
            entity_id=column.id, table_id=column.table_id, name=column.name, display_name=key, text="",
            score=score, rerank_score=rerank,
        )

    def find(self, hits, reranked=True):
        outcome = TopicSearchOutcome(hits=hits, reranked=reranked)
        return FieldService(self.session, FakeSearch(outcome), SimpleNamespace()).find(self.connection.id, "q")

    def test_fields_are_grouped_by_table_and_filtered_by_the_jev_threshold(self) -> None:
        result = self.find([
            self.hit("orders.total", 0.9, 0.95), self.hit("customers.name", 0.8, 0.7),
            self.hit("items.qty", 0.5, 0.59), self.hit("orders.ship_to", 0.4, 0.61),
        ])
        self.assertEqual([table.name for table in result.tables], ["public.orders", "public.customers"])
        self.assertEqual([item.name for item in result.tables[0].fields], ["total", "ship_to"])
        self.assertEqual(result.match, "ok")

    def test_nothing_above_the_threshold_returns_none(self) -> None:
        result = self.find([self.hit("orders.total", 0.9, 0.3)])
        self.assertEqual((result.tables, result.match), ([], "none"))
        self.assertIn("hỏi lại", result.note)

    def test_without_rerank_everything_is_returned_as_unverified(self) -> None:
        result = self.find([self.hit("orders.total", 0.9, None)], reranked=False)
        self.assertEqual(result.match, "unverified")
        self.assertEqual(len(result.tables[0].fields), 1)


if __name__ == "__main__":
    unittest.main()
