"""CHATSQL Semantic Relationship & Join-Path Reasoner (Phase 6B)."""

from __future__ import annotations

from chatsql.domain.catalog import DatabaseCatalog, TableInfo
from chatsql.domain.inference_case import InferenceCase
from chatsql.grounding.base import GroundingResult
from chatsql.relationships.graph import SchemaRelationshipGraph
from chatsql.relationships.models import Cardinality, RelationshipEdge, RelationshipPlan
from chatsql.text_utils import tokenize as _tokenize


def _is_junction_table(table: TableInfo) -> bool:
    """A pure associative/junction table: its primary key is entirely foreign keys.

    ``Cardinality`` is assigned per FK edge (which is inherently ONE_TO_ONE or
    MANY_TO_ONE from the child's side) and can never itself be MANY_TO_MANY, so
    many-to-many fan-out risk is instead detected structurally: a table whose
    primary key is composed of two or more foreign-key columns is a junction
    table, and traversing through one is where row-multiplying fan-out happens.
    """
    pk = [c for c in table.columns if c.is_primary_key]
    return len(pk) >= 2 and all(c.is_foreign_key for c in pk)


class SemanticRelationshipReasoner:
    """Advanced multi-hop join reasoner with semantic role scoring and grain validation."""

    def __init__(
        self,
        max_join_depth: int = 3,
        allow_bridge_tables: bool = True,
        validate_grain: bool = True,
        cardinality_penalty: float = 0.8,
    ) -> None:
        self.max_join_depth = max_join_depth
        self.allow_bridge_tables = allow_bridge_tables
        self.validate_grain = validate_grain
        self.cardinality_penalty = cardinality_penalty

    def reason(
        self,
        case: InferenceCase,
        catalog: DatabaseCatalog,
        grounding: GroundingResult | None = None,
    ) -> RelationshipPlan:
        """Construct an optimal RelationshipPlan for an InferenceCase."""
        if grounding is not None and grounding.tables:
            candidate_tables = {t.name for t in grounding.tables}
        else:
            candidate_tables = {t.name for t in catalog.tables}

        # Filter candidate tables to those that exist in catalog
        valid_tables = {t for t in candidate_tables if any(cat.name == t for cat in catalog.tables)}
        if not valid_tables:
            return RelationshipPlan(tables=(), edges=(), grain=(), confidence=0.0)

        if len(valid_tables) == 1:
            table_map = {t.name: t for t in catalog.tables}
            grain = self._infer_single_table_grain(list(valid_tables)[0], table_map)
            return RelationshipPlan(
                tables=tuple(sorted(valid_tables)),
                edges=(),
                grain=grain,
                evidence=({"strategy": "single_table_no_join"},),
                confidence=1.0,
            )

        graph = SchemaRelationshipGraph(catalog)
        table_map = {t.name: t for t in catalog.tables}
        query_text = case.question
        if case.evidence and isinstance(case.evidence, dict):
            query_text += " " + " ".join(str(v) for v in case.evidence.values())
        query_tokens = _tokenize(query_text)

        # Connect candidate tables into a connected component
        connected_tables, selected_edges, confidence = self._plan_joins(
            valid_tables,
            graph,
            query_tokens,
            table_map,
        )

        grain = self._infer_grain(connected_tables, selected_edges, query_tokens, table_map)

        return RelationshipPlan(
            tables=tuple(sorted(connected_tables)),
            edges=tuple(selected_edges),
            grain=grain,
            evidence=(
                {
                    "reasoner": "semantic_relationship_reasoner",
                    "hop_count": len(selected_edges),
                    "bridge_tables": sorted(connected_tables - valid_tables),
                },
            ),
            confidence=round(confidence, 3),
        )

    def _plan_joins(
        self,
        target_tables: set[str],
        graph: SchemaRelationshipGraph,
        query_tokens: set[str],
        table_map: dict[str, TableInfo],
    ) -> tuple[set[str], list[RelationshipEdge], float]:
        """Connect target tables using semantically scored paths."""
        sorted_targets = sorted(target_tables)
        connected: set[str] = {sorted_targets[0]}
        unconnected: set[str] = set(sorted_targets[1:])
        selected_edges: list[RelationshipEdge] = []
        seen_edges: set[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = set()
        path_confidences: list[float] = []

        while unconnected:
            best_score = -1e9
            best_path: list[RelationshipEdge] | None = None
            best_target: str | None = None

            for start in sorted(connected):
                for target in sorted(unconnected):
                    candidate_paths = graph.find_paths_between(
                        start,
                        target,
                        max_depth=self.max_join_depth,
                    )
                    for path in candidate_paths:
                        # Check bridge table allowance
                        intermediate_tables = {
                            t for edge in path for t in (edge.left_table, edge.right_table)
                        } - {start, target}
                        if not self.allow_bridge_tables and intermediate_tables:
                            continue

                        score = self._score_path(path, query_tokens, table_map)
                        if score > best_score:
                            best_score = score
                            best_path = path
                            best_target = target

            if best_path is None or best_target is None:
                if not self.allow_bridge_tables:
                    return connected, selected_edges, 0.0

                # Disconnected component: bridge only the still-unreached tables
                # onto the existing connected component, instead of discarding
                # the edges already chosen by semantic scoring.
                bridge_tables, bridge_edges = graph.connect_tables_shortest(
                    connected | unconnected, already_connected=connected
                )
                bridge_hop_count = 0
                for edge in bridge_edges:
                    key = (
                        edge.left_table,
                        edge.right_table,
                        edge.left_columns,
                        edge.right_columns,
                    )
                    if key not in seen_edges:
                        seen_edges.add(key)
                        selected_edges.append(edge)
                        bridge_hop_count += 1

                total_hops = len(path_confidences) + bridge_hop_count
                if total_hops:
                    fallback_confidence = (
                        sum(path_confidences) + 0.5 * bridge_hop_count
                    ) / total_hops
                else:
                    fallback_confidence = 0.5
                return connected | bridge_tables, selected_edges, fallback_confidence

            for edge in best_path:
                key = (edge.left_table, edge.right_table, edge.left_columns, edge.right_columns)
                if key not in seen_edges:
                    seen_edges.add(key)
                    selected_edges.append(edge)
                connected.add(edge.left_table)
                connected.add(edge.right_table)

            unconnected.discard(best_target)
            path_confidences.append(min(1.0, max(0.2, best_score / 20.0)))

        avg_conf = sum(path_confidences) / len(path_confidences) if path_confidences else 1.0
        return connected, selected_edges, avg_conf

    def _score_path(
        self,
        path: list[RelationshipEdge],
        query_tokens: set[str],
        table_map: dict[str, TableInfo],
    ) -> float:
        """Score a candidate path considering role disambiguation and cardinality."""
        # Baseline score inversely proportional to path length
        score = 25.0 / (1.0 + len(path))

        for edge in path:
            # 1. Role semantic match on FK column names
            # E.g., for flight departures vs arrivals, column name 'departure_airport'
            for col in edge.left_columns:
                score += 3.0 * len(query_tokens & _tokenize(col))
            for col in edge.right_columns:
                score += 3.0 * len(query_tokens & _tokenize(col))

            # 2. Table name & description matches
            for tbl_name in (edge.left_table, edge.right_table):
                tbl = table_map.get(tbl_name)
                if tbl:
                    score += 2.0 * len(query_tokens & _tokenize(tbl.name))
                    score += 1.0 * len(query_tokens & _tokenize(tbl.description))

            # 3. Cardinality validation: 1-to-1 is safe and preserves grain
            if self.validate_grain and edge.cardinality == Cardinality.ONE_TO_ONE.value:
                score += 2.0

        # 4. Fan-out penalty: a path through a junction/bridge table implies a
        # many-to-many relationship even though each individual FK edge is
        # itself ONE_TO_ONE or MANY_TO_ONE (see _is_junction_table).
        if self.validate_grain:
            junction_tables = {
                tbl_name
                for edge in path
                for tbl_name in (edge.left_table, edge.right_table)
                if (tbl := table_map.get(tbl_name)) and _is_junction_table(tbl)
            }
            score *= self.cardinality_penalty**len(junction_tables)

        return score

    def _infer_single_table_grain(
        self,
        table_name: str,
        table_map: dict[str, TableInfo],
    ) -> tuple[str, ...]:
        table = table_map.get(table_name)
        if table:
            pk = tuple(c.name for c in table.columns if c.is_primary_key)
            if pk:
                return pk
        return (table_name,)

    def _infer_grain(
        self,
        tables: set[str],
        edges: list[RelationshipEdge],
        query_tokens: set[str],
        table_map: dict[str, TableInfo],
    ) -> tuple[str, ...]:
        """Infer the target row grain of the query result."""
        # Find root/primary entity table that matches question tokens most strongly
        best_table: str | None = None
        max_score = -1.0

        for t_name in sorted(tables):
            t_info = table_map.get(t_name)
            if not t_info:
                continue
            s = len(query_tokens & _tokenize(t_name)) * 3.0
            pk = tuple(c.name for c in t_info.columns if c.is_primary_key)
            if pk:
                s += 1.0
            if s > max_score:
                max_score = s
                best_table = t_name

        if best_table:
            t_info = table_map.get(best_table)
            if t_info:
                pk = tuple(c.name for c in t_info.columns if c.is_primary_key)
                if pk:
                    return tuple(f"{best_table}.{col}" for col in pk)
            return (best_table,)

        return tuple(sorted(tables))
