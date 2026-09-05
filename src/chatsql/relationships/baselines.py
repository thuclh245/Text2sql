"""Baseline path finders for relationship reasoning experiments (Phase 6B)."""

from __future__ import annotations

from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.inference_case import InferenceCase
from chatsql.relationships.graph import SchemaRelationshipGraph
from chatsql.relationships.models import RelationshipEdge, RelationshipPlan
from chatsql.text_utils import tokenize as _tokenize


class DeclaredFKShortestPathBaseline:
    """Baseline 1: Connects tables via declared FK shortest path (Steiner approx)."""

    def plan(
        self,
        tables: set[str],
        catalog: DatabaseCatalog,
        case: InferenceCase | None = None,
    ) -> RelationshipPlan:
        graph = SchemaRelationshipGraph(catalog)
        all_tables, edges = graph.connect_tables_shortest(tables)
        return RelationshipPlan(
            tables=tuple(sorted(all_tables)),
            edges=tuple(edges),
            grain=tuple(sorted(tables)),
            evidence=({"baseline": "declared_fk_shortest_path"},),
            confidence=1.0,
        )


class MinimumHopHeuristicBaseline:
    """Baseline 2: Candidate path generation with minimum-hop and deterministic tie-breaking."""

    def plan(
        self,
        tables: set[str],
        catalog: DatabaseCatalog,
        case: InferenceCase | None = None,
    ) -> RelationshipPlan:
        graph = SchemaRelationshipGraph(catalog)
        if len(tables) <= 1:
            return RelationshipPlan(
                tables=tuple(sorted(tables)),
                edges=(),
                grain=tuple(sorted(tables)),
                evidence=({"baseline": "minimum_hop_heuristic"},),
                confidence=1.0,
            )

        # Connect pairs using shortest paths, breaking ties by table name sort
        sorted_tables = sorted(tables)
        connected: set[str] = {sorted_tables[0]}
        remaining = set(sorted_tables[1:])
        selected_edges: list[RelationshipEdge] = []
        seen_edges: set[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = set()

        while remaining:
            best_path: list[RelationshipEdge] | None = None
            best_target: str | None = None

            for src in sorted(connected):
                for tgt in sorted(remaining):
                    paths = graph.find_paths_between(src, tgt, max_depth=4)
                    if not paths:
                        continue
                    # Best path is shortest; ties broken by alphabetical table names
                    candidate = paths[0]
                    if best_path is None or len(candidate) < len(best_path):
                        best_path = candidate
                        best_target = tgt

            if best_path is None or best_target is None:
                break

            for edge in best_path:
                key = (edge.left_table, edge.right_table, edge.left_columns, edge.right_columns)
                if key not in seen_edges:
                    seen_edges.add(key)
                    selected_edges.append(edge)
                connected.add(edge.left_table)
                connected.add(edge.right_table)

            remaining.discard(best_target)

        return RelationshipPlan(
            tables=tuple(sorted(connected)),
            edges=tuple(selected_edges),
            grain=tuple(sorted(tables)),
            evidence=({"baseline": "minimum_hop_heuristic"},),
            confidence=0.9,
        )


class LexicalRerankerBaseline:
    """Baseline 3: Candidate path enumeration scored against question text tokens."""

    def __init__(self, max_depth: int = 3) -> None:
        self.max_depth = max_depth

    def plan(
        self,
        tables: set[str],
        catalog: DatabaseCatalog,
        case: InferenceCase,
    ) -> RelationshipPlan:
        graph = SchemaRelationshipGraph(catalog)
        if len(tables) <= 1:
            return RelationshipPlan(
                tables=tuple(sorted(tables)),
                edges=(),
                grain=tuple(sorted(tables)),
                evidence=({"baseline": "lexical_reranker"},),
                confidence=1.0,
            )

        q_tokens = _tokenize(case.question)
        if case.evidence and isinstance(case.evidence, dict):
            q_tokens |= _tokenize(" ".join(str(v) for v in case.evidence.values()))

        # For pairs of tables, score candidate paths based on column and bridge table overlap
        table_list = sorted(tables)
        src = table_list[0]
        connected: set[str] = {src}
        remaining = set(table_list[1:])
        selected_edges: list[RelationshipEdge] = []
        seen_edges: set[tuple[str, str, tuple[str, ...], tuple[str, ...]]] = set()

        while remaining:
            best_score = -1.0
            best_path: list[RelationshipEdge] | None = None
            best_target: str | None = None

            for start in sorted(connected):
                for target in sorted(remaining):
                    candidate_paths = graph.find_paths_between(
                        start, target, max_depth=self.max_depth
                    )
                    for path in candidate_paths:
                        score = self._score_path(path, q_tokens, catalog)
                        if score > best_score:
                            best_score = score
                            best_path = path
                            best_target = target

            if best_path is None or best_target is None:
                break

            for edge in best_path:
                key = (edge.left_table, edge.right_table, edge.left_columns, edge.right_columns)
                if key not in seen_edges:
                    seen_edges.add(key)
                    selected_edges.append(edge)
                connected.add(edge.left_table)
                connected.add(edge.right_table)

            remaining.discard(best_target)

        return RelationshipPlan(
            tables=tuple(sorted(connected)),
            edges=tuple(selected_edges),
            grain=tuple(sorted(tables)),
            evidence=({"baseline": "lexical_reranker", "score": best_score},),
            confidence=0.85,
        )

    def _score_path(
        self,
        path: list[RelationshipEdge],
        query_tokens: set[str],
        catalog: DatabaseCatalog,
    ) -> float:
        # Penalize longer paths slightly, reward lexical match on involved join columns & tables
        score = 10.0 / (1.0 + len(path))
        for edge in path:
            score += 2.0 * len(query_tokens & _tokenize(edge.left_table))
            score += 2.0 * len(query_tokens & _tokenize(edge.right_table))
            for col in edge.left_columns:
                score += 1.5 * len(query_tokens & _tokenize(col))
            for col in edge.right_columns:
                score += 1.5 * len(query_tokens & _tokenize(col))
        return score
