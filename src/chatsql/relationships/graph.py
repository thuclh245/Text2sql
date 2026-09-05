"""Relational schema graph with multi-edge support and path finding."""

from __future__ import annotations

from collections import deque
import heapq
from typing import Iterator

from chatsql.domain.catalog import DatabaseCatalog, TableInfo
from chatsql.relationships.models import Cardinality, RelationType, RelationshipEdge


class SchemaRelationshipGraph:
    """Multi-edge relationship graph built from DatabaseCatalog metadata."""

    def __init__(self, catalog: DatabaseCatalog) -> None:
        self.catalog = catalog
        self.tables = {table.name: table for table in catalog.tables}
        self._adj: dict[str, list[RelationshipEdge]] = {table.name: [] for table in catalog.tables}
        self._all_edges: list[RelationshipEdge] = []
        self._build_graph()

    @property
    def all_edges(self) -> tuple[RelationshipEdge, ...]:
        """All relationship edges in the catalog."""
        return tuple(self._all_edges)

    def neighbors(self, table: str) -> set[str]:
        """Return all adjacent tables connected by at least one relationship edge."""
        return {edge.other_table(table) for edge in self._adj.get(table, [])}

    def edges_between(self, table_a: str, table_b: str) -> list[RelationshipEdge]:
        """Return all direct edges connecting table_a and table_b."""
        return [
            edge
            for edge in self._adj.get(table_a, [])
            if edge.other_table(table_a) == table_b
        ]

    def shortest_path(
        self,
        source: str,
        target: str,
    ) -> list[RelationshipEdge] | None:
        """Find the shortest edge-path between source and target using BFS."""
        if source == target:
            return []
        if source not in self.tables or target not in self.tables:
            return None

        visited: set[str] = {source}
        # queue of (current_table, path_of_edges)
        queue: deque[tuple[str, list[RelationshipEdge]]] = deque([(source, [])])

        while queue:
            current, path = queue.popleft()
            if current == target:
                return path

            for edge in sorted(self._adj.get(current, []), key=lambda e: (e.left_table, e.right_table)):
                neighbor = edge.other_table(current)
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [edge]))

        return None

    def find_paths_between(
        self,
        source: str,
        target: str,
        max_depth: int = 3,
    ) -> list[list[RelationshipEdge]]:
        """Find all simple paths between source and target up to max_depth hops."""
        if source == target or source not in self.tables or target not in self.tables:
            return []

        results: list[list[RelationshipEdge]] = []

        def dfs(current: str, current_path: list[RelationshipEdge], visited_nodes: set[str]) -> None:
            if len(current_path) > max_depth:
                return
            if current == target:
                results.append(list(current_path))
                return

            for edge in self._adj.get(current, []):
                neighbor = edge.other_table(current)
                if neighbor not in visited_nodes:
                    visited_nodes.add(neighbor)
                    current_path.append(edge)
                    dfs(neighbor, current_path, visited_nodes)
                    current_path.pop()
                    visited_nodes.remove(neighbor)

        dfs(source, [], {source})
        # Sort paths by length, then string representation for determinism
        results.sort(key=lambda p: (len(p), [e.canonical_pair() for e in p]))
        return results

    def connect_tables_shortest(
        self,
        required_tables: set[str],
    ) -> tuple[set[str], list[RelationshipEdge]]:
        """Connect all required tables using shortest paths (Steiner-like approximation).

        Returns:
            (all_tables_including_bridges, selected_edges)
        """
        if not required_tables:
            return set(), []
        if len(required_tables) == 1:
            return set(required_tables), []

        # Deterministic order
        sorted_tables = sorted(required_tables)
        connected_tables: set[str] = {sorted_tables[0]}
        unconnected_tables = set(sorted_tables[1:])
        selected_edges: list[RelationshipEdge] = []
        seen_edges: set[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = set()

        while unconnected_tables:
            best_path: list[RelationshipEdge] | None = None
            best_target: str | None = None

            for start in sorted(connected_tables):
                for target in sorted(unconnected_tables):
                    path = self.shortest_path(start, target)
                    if path is not None:
                        if best_path is None or len(path) < len(best_path):
                            best_path = path
                            best_target = target

            if best_path is None or best_target is None:
                # Disconnected graph component
                break

            for edge in best_path:
                edge_id = (
                    edge.left_table,
                    edge.right_table,
                    edge.left_columns,
                    edge.right_columns,
                )
                if edge_id not in seen_edges:
                    seen_edges.add(edge_id)
                    selected_edges.append(edge)
                connected_tables.add(edge.left_table)
                connected_tables.add(edge.right_table)

            unconnected_tables.discard(best_target)

        return connected_tables, selected_edges

    def _build_graph(self) -> None:
        seen: set[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = set()

        for table in self.catalog.tables:
            for column in table.columns:
                if not column.is_foreign_key or not column.references:
                    continue

                ref_table, ref_col = self._parse_reference(column.references)
                if not ref_table or ref_table not in self.tables:
                    continue

                ref_table_info = self.tables[ref_table]
                left_cols = (column.name,)
                right_cols = (ref_col,) if ref_col else (ref_table_info.primary_key or (ref_table_info.columns[0].name if ref_table_info.columns else ""),)

                cardinality = self._infer_cardinality(table, column, ref_table_info)

                edge = RelationshipEdge(
                    left_table=table.name,
                    right_table=ref_table,
                    left_columns=left_cols,
                    right_columns=right_cols,
                    relation_type=RelationType.FOREIGN_KEY.value,
                    cardinality=cardinality.value,
                    provenance="declared_fk",
                    confidence=1.0,
                )

                edge_key = (table.name, ref_table, left_cols, right_cols)
                if edge_key not in seen:
                    seen.add(edge_key)
                    self._all_edges.append(edge)
                    self._adj[table.name].append(edge)
                    self._adj[ref_table].append(edge)

    def _infer_cardinality(
        self,
        source_table: TableInfo,
        source_col: Any,
        target_table: TableInfo,
    ) -> Cardinality:
        """Infer cardinality based on PK/unique constraints."""
        is_src_pk = source_col.is_primary_key or (
            source_table.primary_key and source_table.primary_key == (source_col.name,)
        )
        # If the FK column in the child table is also the primary key of the child table,
        # it is a 1-to-1 relationship (e.g. extension table). Otherwise many-to-one.
        if is_src_pk:
            return Cardinality.ONE_TO_ONE
        return Cardinality.MANY_TO_ONE

    @staticmethod
    def _parse_reference(reference: str) -> tuple[str | None, str | None]:
        ref = reference.strip()
        parts = [p.strip('`"[] ') for p in ref.split(".")]
        if len(parts) >= 2:
            return parts[-2], parts[-1]
        if len(parts) == 1 and parts[0]:
            return parts[0], None
        return None, None
