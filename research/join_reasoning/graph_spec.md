# Phase 6B Relationship Graph Specification

## 1. Relational Graph Model
The database relational graph $G = (V, E)$ represents tables as nodes $V$ and foreign-key / semantic connections as edges $E$.

Unlike simple undirected graph representations, the relationship graph supports:
1. **Multi-edges**: Multiple distinct foreign keys connecting the same pair of tables (e.g. `flights.departure_airport -> airports.airport_code` and `flights.arrival_airport -> airports.airport_code`).
2. **Cardinality Annotations**:
   - `ONE_TO_ONE`: Child FK column is also a primary key.
   - `MANY_TO_ONE`: Child FK references parent PK.
   - `ONE_TO_MANY`: Inverted relationship view.
   - `MANY_TO_MANY`: Bridge/junction table decomposition.
3. **Compound Foreign Keys**: Multi-column key relationships represented as tuples of column pairs.

## 2. RelationshipEdge IR
```python
@dataclass(frozen=True)
class RelationshipEdge:
    left_table: str
    right_table: str
    left_columns: tuple[str, ...]
    right_columns: tuple[str, ...]
    relation_type: str = "FOREIGN_KEY"  # FOREIGN_KEY | IMPLICIT | INFERRED
    cardinality: str | None = None
    provenance: str = "declared_fk"
    confidence: float | None = 1.0
```

## 3. RelationshipPlan IR
```python
@dataclass(frozen=True)
class RelationshipPlan:
    tables: tuple[str, ...]
    edges: tuple[RelationshipEdge, ...]
    grain: tuple[str, ...]
    evidence: tuple[dict[str, Any], ...] = ()
    confidence: float | None = 1.0
```

## 4. Multi-hop Path Resolution
- **Bridge Table Resolution**: When two candidate tables lack direct foreign key edges, the graph search finds the minimal intermediate bridge tables required to establish connectivity without introducing extraneous nodes.
- **Role Disambiguation**: When multiple candidate edges exist between nodes, the reasoner scores each edge by lexical and semantic overlap between the query tokens and the edge column names and table descriptions.
