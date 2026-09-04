"""Schema relationship graph utilities for grounding research."""

from __future__ import annotations

from collections import deque

from chatsql.domain.catalog import DatabaseCatalog

RelationshipGraph = dict[str, set[str]]


def build_relationship_graph(catalog: DatabaseCatalog) -> RelationshipGraph:
    """Build an undirected table graph from declared foreign-key metadata."""
    table_names = {table.name for table in catalog.tables}
    graph: RelationshipGraph = {table.name: set() for table in catalog.tables}

    for table in catalog.tables:
        for column in table.columns:
            if not column.is_foreign_key or not column.references:
                continue
            target_table = _parse_reference_table(column.references)
            if target_table is None or target_table not in table_names:
                continue
            graph[table.name].add(target_table)
            graph[target_table].add(table.name)

    return graph


def expand_fk_neighbors(
    seed_tables: set[str],
    graph: RelationshipGraph,
    depth: int,
    include_fk_neighbors: bool = True,
) -> set[str]:
    """Return seed tables plus FK neighbors reachable within ``depth`` hops."""
    if depth <= 0 or not include_fk_neighbors:
        return set(seed_tables)

    expanded = set(seed_tables)
    queue: deque[tuple[str, int]] = deque((table, 0) for table in sorted(seed_tables))

    while queue:
        table, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        for neighbor in sorted(graph.get(table, ())):
            if neighbor in expanded:
                continue
            expanded.add(neighbor)
            queue.append((neighbor, current_depth + 1))

    return expanded


def _parse_reference_table(reference: str) -> str | None:
    reference = reference.strip()
    if "." not in reference:
        return None
    table_name, _ = reference.split(".", 1)
    table_name = table_name.strip('`"[] ')
    return table_name or None
