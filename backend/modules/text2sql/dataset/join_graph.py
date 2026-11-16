import hashlib
from collections import deque
from dataclasses import dataclass
from uuid import UUID

from ..common.errors import Text2SqlInvalidRequest
from ..query.compiler import quote
from ..vector_store.ingestion.documents.context import CatalogContext
from .join_schemas import JoinEdge, JoinOption, JoinPlan, JoinStep

MAX_TABLES = 8
MAX_ALTERNATIVES = 4
NOT_DECLARED_HINT = "Hãy khai báo cột tham chiếu (referenced_column) trong data dictionary rồi hỏi lại."


@dataclass(frozen=True)
class _Hop:
    edge: JoinEdge
    from_table: UUID
    to_table: UUID

    @property
    def multiplies(self) -> bool:
        return self.from_table == self.edge.parent_table_id or not self.edge.parent_is_unique


def build_edges(context: CatalogContext) -> list[JoinEdge]:
    edges: list[JoinEdge] = []
    for entry in context.columns:
        dictionary = entry.dictionary
        parent = context.columns_by_id.get(dictionary.referenced_column_id) if dictionary else None
        if parent is None or parent.column.table_id == entry.column.table_id:
            continue
        child_table = context.tables[entry.column.table_id]
        parent_table = context.tables[parent.column.table_id]
        parent_dictionary = parent.dictionary
        unique = bool(parent_dictionary and (parent_dictionary.is_primary_key or parent_dictionary.is_unique))
        edges.append(JoinEdge(
            edge_id=entry.column.id, child_table_id=child_table.table.id, child_column_id=entry.column.id,
            parent_table_id=parent_table.table.id, parent_column_id=parent.column.id,
            child_table=child_table.qualified_name, child_column=entry.column.name,
            parent_table=parent_table.qualified_name, parent_column=parent.column.name, parent_is_unique=unique,
        ))
    return edges


class JoinGraph:
    def __init__(self, context: CatalogContext) -> None:
        self.context = context
        self.edges = {edge.edge_id: edge for edge in build_edges(context)}
        self.adjacent: dict[UUID, list[_Hop]] = {}
        for edge in self.edges.values():
            self._link(_Hop(edge, edge.child_table_id, edge.parent_table_id))
            self._link(_Hop(edge, edge.parent_table_id, edge.child_table_id))

    def _link(self, hop: _Hop) -> None:
        self.adjacent.setdefault(hop.from_table, []).append(hop)

    def plan(
        self, table_ids: list[UUID], via: list[UUID] | None = None, root: UUID | None = None,
    ) -> JoinPlan:
        tables = list(dict.fromkeys(table_ids))
        unknown = [str(item) for item in tables if item not in self.context.tables]
        if unknown:
            raise Text2SqlInvalidRequest(f"Bảng không thuộc connection: {', '.join(unknown)}.")
        if not tables or len(tables) > MAX_TABLES:
            raise Text2SqlInvalidRequest(f"Cần từ 1 đến {MAX_TABLES} bảng.")
        forced = list(dict.fromkeys(via or []))
        missing = [str(item) for item in forced if item not in self.edges]
        if missing:
            raise Text2SqlInvalidRequest(f"Quan hệ không tồn tại: {', '.join(missing)}.")
        if root is not None and root not in tables:
            raise Text2SqlInvalidRequest("Bảng gốc phải nằm trong danh sách bảng cần nối.")
        if len(tables) == 1 and not forced:
            return JoinPlan(status="ok", options=[self._option(tables[0], [])])
        trees = self._trees(tables, forced)
        if trees is None:
            return JoinPlan(status="not_declared", message=self._not_declared(tables))
        options = [self._option(root, edges) for root, edges in self._rooted(trees, root)]
        if len(options) == 1:
            return JoinPlan(status="ok", options=options)
        return JoinPlan(
            status="ambiguous", options=options,
            message="Có nhiều cách nối các bảng; hãy chọn một phương án và gửi lại edge_ids của phương án đó.",
        )

    def _label(self, table_id: UUID) -> str:
        return self.context.tables[table_id].qualified_name

    def _not_declared(self, tables: list[UUID]) -> str:
        groups = " | ".join(", ".join(self._label(item) for item in group) for group in self._components(tables))
        return f"Chưa có quan hệ khai báo nối các nhóm bảng: {groups}. {NOT_DECLARED_HINT}"

    def _components(self, tables: list[UUID]) -> list[list[UUID]]:
        remaining = list(tables)
        groups: list[list[UUID]] = []
        while remaining:
            reach = {remaining[0]}
            queue = deque(reach)
            while queue:
                for hop in self.adjacent.get(queue.popleft(), []):
                    if hop.to_table not in reach:
                        reach.add(hop.to_table)
                        queue.append(hop.to_table)
            groups.append([item for item in remaining if item in reach])
            remaining = [item for item in remaining if item not in reach]
        return groups

    def _paths(self, sources: set[UUID], target: UUID) -> list[list[_Hop]] | None:
        distance = {item: 0 for item in sources}
        parents: dict[UUID, list[_Hop]] = {item: [] for item in sources}
        queue = deque(sources)
        while queue:
            current = queue.popleft()
            for hop in self.adjacent.get(current, []):
                step = distance[current] + 1
                if hop.to_table not in distance:
                    distance[hop.to_table] = step
                    parents[hop.to_table] = [hop]
                    queue.append(hop.to_table)
                elif distance[hop.to_table] == step:
                    parents[hop.to_table].append(hop)
        if target not in distance:
            return None
        paths: list[list[_Hop]] = []

        def walk(node: UUID, tail: list[_Hop]) -> None:
            if len(paths) >= MAX_ALTERNATIVES:
                return
            if node in sources:
                paths.append(list(reversed(tail)))
                return
            for hop in parents[node]:
                walk(hop.from_table, [*tail, hop])

        walk(target, [])
        return paths

    def _trees(self, tables: list[UUID], forced: list[UUID]) -> list[frozenset[UUID]] | None:
        forced_edges = frozenset(forced)
        anchors = {tables[0]} | self._nodes(forced_edges)
        solutions: list[frozenset[UUID]] = [forced_edges]
        for target in [item for item in tables if item not in anchors]:
            expanded: list[frozenset[UUID]] = []
            for partial in solutions:
                nodes = self._nodes(partial) | anchors
                if target in nodes:
                    expanded.append(partial)
                    continue
                paths = self._paths(nodes, target)
                if paths is None:
                    return None
                expanded.extend(partial | {hop.edge.edge_id for hop in path} for path in paths)
            solutions = list(dict.fromkeys(expanded))[:MAX_ALTERNATIVES]
            anchors.add(target)
        connected = [tree for tree in solutions if self._is_connected(tables, tree)]
        return connected or None

    def _nodes(self, edge_ids: frozenset[UUID]) -> set[UUID]:
        nodes: set[UUID] = set()
        for edge_id in edge_ids:
            edge = self.edges[edge_id]
            nodes |= {edge.child_table_id, edge.parent_table_id}
        return nodes

    def _is_connected(self, tables: list[UUID], edge_ids: frozenset[UUID]) -> bool:
        nodes = self._nodes(edge_ids) | set(tables)
        seen = {tables[0]}
        queue = deque(seen)
        while queue:
            current = queue.popleft()
            for edge_id in edge_ids:
                edge = self.edges[edge_id]
                for here, there in (
                    (edge.child_table_id, edge.parent_table_id), (edge.parent_table_id, edge.child_table_id),
                ):
                    if here == current and there not in seen:
                        seen.add(there)
                        queue.append(there)
        return seen >= nodes

    def _rooted(
        self, trees: list[frozenset[UUID]], fixed_root: UUID | None = None,
    ) -> list[tuple[UUID, list[JoinEdge]]]:
        result = []
        for tree in trees:
            edges = [self.edges[item] for item in sorted(tree, key=str)]
            nodes = sorted(self._nodes(tree), key=self._label)
            root = fixed_root or min(nodes, key=lambda item: (self._multiplications(item, edges), self._label(item)))
            result.append((root, edges))
        return result

    def _walk(self, root: UUID, edges: list[JoinEdge]) -> list[_Hop]:
        remaining = list(edges)
        reached = {root}
        order: list[_Hop] = []
        progress = True
        while remaining and progress:
            progress = False
            for edge in list(remaining):
                if edge.child_table_id in reached and edge.parent_table_id not in reached:
                    hop = _Hop(edge, edge.child_table_id, edge.parent_table_id)
                elif edge.parent_table_id in reached and edge.child_table_id not in reached:
                    hop = _Hop(edge, edge.parent_table_id, edge.child_table_id)
                else:
                    continue
                order.append(hop)
                reached.add(hop.to_table)
                remaining.remove(edge)
                progress = True
        return order

    def _multiplications(self, root: UUID, edges: list[JoinEdge]) -> int:
        return sum(1 for hop in self._walk(root, edges) if hop.multiplies)

    def _option(self, root: UUID, edges: list[JoinEdge]) -> JoinOption:
        order = self._walk(root, edges)
        aliases = {root: "t1"}
        for index, hop in enumerate(order, start=2):
            aliases[hop.to_table] = f"t{index}"
        from_sql = f"FROM {self._source(root, aliases)}"
        steps: list[JoinStep] = []
        warnings: list[str] = []
        for hop in order:
            edge = hop.edge
            on = (
                f"{aliases[edge.child_table_id]}.{quote(edge.child_column)} = "
                f"{aliases[edge.parent_table_id]}.{quote(edge.parent_column)}"
            )
            from_sql += f"\nLEFT JOIN {self._source(hop.to_table, aliases)} ON {on}"
            steps.append(JoinStep(
                alias=aliases[hop.to_table], table_id=hop.to_table, table=self._label(hop.to_table),
                joined_from=aliases[hop.from_table], on=on, edge_id=edge.edge_id, multiplies_rows=hop.multiplies,
            ))
            if hop.multiplies:
                warnings.append(
                    f"Nối {self._label(hop.to_table)} làm nhân số dòng của {self._label(hop.from_table)}; "
                    "tổng hợp (SUM, COUNT) cột của bảng trước đó có thể bị cộng trùng."
                )
        key = "|".join(sorted(str(hop.edge.edge_id) for hop in order)) or str(root)
        return JoinOption(
            signature=hashlib.sha256(key.encode()).hexdigest()[:32], root_table_id=root, from_sql=from_sql,
            steps=steps, edge_ids=[hop.edge.edge_id for hop in order], table_ids=list(aliases),
            aliases={alias: self._label(table) for table, alias in aliases.items()}, warnings=warnings,
        )

    def _source(self, table_id: UUID, aliases: dict[UUID, str]) -> str:
        entry = self.context.tables[table_id]
        return f"{quote(entry.schema.name)}.{quote(entry.table.name)} AS {aliases[table_id]}"
