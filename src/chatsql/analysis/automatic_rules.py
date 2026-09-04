"""Automatic diagnostic rules for pre-labeling Text-to-SQL errors (P5-T01)."""

from __future__ import annotations

import re
from typing import Any

import sqlglot
from sqlglot import exp

from chatsql.analysis.taxonomy import LabeledCase
from chatsql.domain.catalog import DatabaseCatalog
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase
from chatsql.domain.result import ExecutionResult, Prediction


def extract_tables_from_sql(sql: str) -> set[str]:
    """Extract table names from SQL using sqlglot AST with regex fallback."""
    tables: set[str] = set()
    try:
        statements = [stmt for stmt in sqlglot.parse(sql, read="sqlite") if stmt is not None]
        for stmt in statements:
            for tbl_node in stmt.find_all(exp.Table):
                if tbl_node.name:
                    tables.add(tbl_node.name.lower())
        if tables:
            return tables
    except Exception:
        pass

    # Fallback to regex
    sql_clean = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
    sql_clean = re.sub(r"/\*.*?\*/", "", sql_clean, flags=re.DOTALL)

    from_match = re.search(
        r"\bFROM\s+(.*?)(?:\bWHERE\b|\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|\bHAVING\b|;|$)",
        sql_clean,
        re.IGNORECASE | re.DOTALL,
    )
    if from_match:
        from_text = from_match.group(1)
        chunks = re.split(
            r",|\bJOIN\b|\bLEFT JOIN\b|\bRIGHT JOIN\b|\bINNER JOIN\b",
            from_text,
            flags=re.IGNORECASE,
        )
        for chunk in chunks:
            chunk_no_on = re.split(r"\bON\b|\bUSING\b", chunk, flags=re.IGNORECASE)[0]
            tokens = chunk_no_on.strip().split()
            if tokens:
                tbl_name = tokens[0].strip('`"[]()').lower()
                if tbl_name and tbl_name not in (
                    "select",
                    "where",
                    "group",
                    "order",
                    "limit",
                    "having",
                    "on",
                    "as",
                    "with",
                ):
                    tables.add(tbl_name)

    join_matches = re.findall(r"\bJOIN\s+([`\"\[]?\w+[`\"\]]?)", sql_clean, re.IGNORECASE)
    for j in join_matches:
        tables.add(j.strip('`"[]()').lower())

    return tables


def extract_columns_from_sql(sql: str) -> set[str]:
    """Extract column names referenced in SQL using sqlglot with regex fallback."""
    cols: set[str] = set()
    try:
        statements = [stmt for stmt in sqlglot.parse(sql, read="sqlite") if stmt is not None]
        for stmt in statements:
            for c in stmt.find_all(exp.Column):
                if c.name and c.name != "*":
                    cols.add(c.name.lower())
        if cols:
            return cols
    except Exception:
        pass

    matches = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)", sql)
    for _, col in matches:
        if col.lower() not in ("sqlite_master",):
            cols.add(col.lower())
    return cols


def extract_aggregations(sql: str) -> set[str]:
    """Extract aggregation function names used in SQL."""
    pattern = r"\b(COUNT|SUM|AVG|MIN|MAX)\s*\("
    matches = re.findall(pattern, sql, re.IGNORECASE)
    return {m.upper() for m in matches}


def extract_time_functions(sql: str) -> set[str]:
    """Extract date/time function keywords used in SQL."""
    pattern = r"\b(STRFTIME|DATE|TIME|DATETIME|JULIANDAY|YEAR|MONTH|DAY)\b"
    matches = re.findall(pattern, sql, re.IGNORECASE)
    return {m.upper() for m in matches}


def extract_where_literals(sql: str) -> set[str]:
    """Extract literal strings/numbers in WHERE clause."""
    where_match = re.search(
        r"\bWHERE\b(.*?)(?:\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|$)", sql, re.IGNORECASE | re.DOTALL
    )
    if not where_match:
        return set()
    where_clause = where_match.group(1)
    strings = set(re.findall(r"['\"]([^'\"]+)['\"]", where_clause))
    return strings


def extract_where_columns(sql: str) -> set[str]:
    """Extract column names appearing in the WHERE clause."""
    try:
        statements = [stmt for stmt in sqlglot.parse(sql, read="sqlite") if stmt is not None]
        cols: set[str] = set()
        for stmt in statements:
            where_node = stmt.find(exp.Where)
            if where_node:
                for c in where_node.find_all(exp.Column):
                    if c.name and c.name != "*":
                        cols.add(c.name.lower())
        if cols:
            return cols
    except Exception:
        pass

    where_match = re.search(
        r"\bWHERE\b(.*?)(?:\bGROUP BY\b|\bORDER BY\b|\bLIMIT\b|$)", sql, re.IGNORECASE | re.DOTALL
    )
    if not where_match:
        return set()
    matches = re.findall(
        r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)", where_match.group(1)
    )
    return {col.lower() for _, col in matches}


def extract_join_keys(sql: str) -> list[tuple[str, str]]:
    """Extract column pairs compared in ON clauses."""
    keys: list[tuple[str, str]] = []
    try:
        statements = [stmt for stmt in sqlglot.parse(sql, read="sqlite") if stmt is not None]
        for stmt in statements:
            for eq in stmt.find_all(exp.EQ):
                if isinstance(eq.left, exp.Column) and isinstance(eq.right, exp.Column):
                    l_name = eq.left.name.lower()
                    r_name = eq.right.name.lower()
                    keys.append((l_name, r_name))
        if keys:
            return keys
    except Exception:
        pass

    on_matches = re.findall(r"\bON\s+([a-zA-Z0-9_.]+)\s*=\s*([a-zA-Z0-9_.]+)", sql, re.IGNORECASE)
    for l_col, r_col in on_matches:
        l_pure = l_col.split(".")[-1].strip('`"[]()').lower()
        r_pure = r_col.split(".")[-1].strip('`"[]()').lower()
        keys.append((l_pure, r_pure))
    return keys


def auto_label_case(
    case: InferenceCase,
    gold: GoldCase,
    prediction: Prediction,
    execution: ExecutionResult,
    execution_correct: bool | None = None,
    catalog: DatabaseCatalog | None = None,
    grounding_metadata: dict[str, Any] | None = None,
) -> LabeledCase:
    """Pre-label a single inference case based on automated diagnostic rules.

    Following diagnostic tree:
    1. Execution correct? -> NONE
    2. Syntax/Runtime/Timeout? -> E41/E42/E91
    3. Missing required tables/columns? -> E01/E02
    4. Wrong relationship/join? -> E10/E12
    5. Wrong aggregation/measure/semantic? -> E21/E20
    6. Value grounding or missing filter? -> E30/E31/E32
    7. Fallback -> E40 (Logical SQL error)
    """
    case_id = case.case_id
    db_id = case.database_id
    question = case.question
    pred_sql = prediction.predicted_sql
    gold_sql = gold.gold_sql
    executed = execution.executed

    correct = execution_correct
    if correct is None:
        correct = getattr(execution, "execution_correct", False)

    if correct:
        return LabeledCase(
            case_id=case_id,
            database_id=db_id,
            question=question,
            predicted_sql=pred_sql,
            gold_sql=gold_sql,
            execution_correct=True,
            primary_error="NONE",
        )

    secondary_errors: list[str] = []

    # 1. Environment / Syntax / Runtime errors
    err_msg = (execution.error or "").lower()
    if "timeout" in err_msg or getattr(execution, "error_kind", "") == "timeout":
        return LabeledCase(
            case_id=case_id,
            database_id=db_id,
            question=question,
            predicted_sql=pred_sql,
            gold_sql=gold_sql,
            execution_correct=False,
            primary_error="E91",
            metadata={"error_detail": execution.error},
        )

    if not executed:
        if getattr(execution, "error_kind", "") == "invalid_sql" or "syntax" in err_msg:
            return LabeledCase(
                case_id=case_id,
                database_id=db_id,
                question=question,
                predicted_sql=pred_sql,
                gold_sql=gold_sql,
                execution_correct=False,
                primary_error="E41",
                metadata={"error_detail": execution.error},
            )
        return LabeledCase(
            case_id=case_id,
            database_id=db_id,
            question=question,
            predicted_sql=pred_sql,
            gold_sql=gold_sql,
            execution_correct=False,
            primary_error="E42",
            metadata={"error_detail": execution.error},
        )

    # 2. Retrieval / Grounding check
    gold_tables = {t.lower() for t in gold.gold_tables}
    if not gold_tables:
        gold_tables = extract_tables_from_sql(gold_sql)

    gold_columns = {c.lower() for c in gold.gold_columns}
    if not gold_columns:
        gold_columns = extract_columns_from_sql(gold_sql)

    # Check grounding result if provided
    if grounding_metadata:
        if "retrieved_tables" in grounding_metadata:
            ret_tbls = {t.lower() for t in grounding_metadata["retrieved_tables"]}
            missing_retrieval_tables = gold_tables - ret_tbls
            if missing_retrieval_tables:
                return LabeledCase(
                    case_id=case_id,
                    database_id=db_id,
                    question=question,
                    predicted_sql=pred_sql,
                    gold_sql=gold_sql,
                    execution_correct=False,
                    primary_error="E01",
                    secondary_errors=tuple(secondary_errors),
                    metadata={"missing_tables": sorted(missing_retrieval_tables)},
                )
            if gold_tables and len(ret_tbls) > (2 * len(gold_tables)):
                secondary_errors.append("E03")

        if "retrieved_columns" in grounding_metadata:
            ret_cols = {c.lower() for c in grounding_metadata["retrieved_columns"]}
            missing_ret_cols = gold_columns - ret_cols
            if missing_ret_cols:
                return LabeledCase(
                    case_id=case_id,
                    database_id=db_id,
                    question=question,
                    predicted_sql=pred_sql,
                    gold_sql=gold_sql,
                    execution_correct=False,
                    primary_error="E02",
                    secondary_errors=tuple(secondary_errors),
                    metadata={"missing_columns": sorted(missing_ret_cols)},
                )
            if gold_columns and len(ret_cols) > (3 * len(gold_columns)):
                secondary_errors.append("E04")

    pred_tables = extract_tables_from_sql(pred_sql)
    missing_pred_tables = gold_tables - pred_tables
    if missing_pred_tables:
        return LabeledCase(
            case_id=case_id,
            database_id=db_id,
            question=question,
            predicted_sql=pred_sql,
            gold_sql=gold_sql,
            execution_correct=False,
            primary_error="E01",
            secondary_errors=tuple(secondary_errors),
            metadata={"missing_tables": sorted(missing_pred_tables)},
        )

    # 3. Relationship / Join check
    gold_has_join = "JOIN" in gold_sql.upper() or len(gold_tables) > 1
    pred_has_join = "JOIN" in pred_sql.upper()
    if gold_has_join and not pred_has_join and len(gold_tables) > 1:
        return LabeledCase(
            case_id=case_id,
            database_id=db_id,
            question=question,
            predicted_sql=pred_sql,
            gold_sql=gold_sql,
            execution_correct=False,
            primary_error="E10",
            secondary_errors=tuple(secondary_errors),
            metadata={
                "reason": (
                    "Gold query requires JOIN across multiple tables but prediction omitted JOIN."
                )
            },
        )

    if gold_has_join and pred_has_join:
        gold_keys = extract_join_keys(gold_sql)
        pred_keys = extract_join_keys(pred_sql)
        if gold_keys and pred_keys and set(gold_keys) != set(pred_keys):
            return LabeledCase(
                case_id=case_id,
                database_id=db_id,
                question=question,
                predicted_sql=pred_sql,
                gold_sql=gold_sql,
                execution_correct=False,
                primary_error="E12",
                secondary_errors=tuple(secondary_errors),
                metadata={"gold_join_keys": gold_keys, "pred_join_keys": pred_keys},
            )

    gold_distinct = "DISTINCT" in gold_sql.upper()
    pred_distinct = "DISTINCT" in pred_sql.upper()
    gold_groupby = "GROUP BY" in gold_sql.upper()
    pred_groupby = "GROUP BY" in pred_sql.upper()
    if (gold_distinct != pred_distinct) or (gold_groupby != pred_groupby):
        secondary_errors.append("E13")

    # 4. Aggregation / Measure check
    gold_aggs = extract_aggregations(gold_sql)
    pred_aggs = extract_aggregations(pred_sql)
    if gold_aggs != pred_aggs and gold_aggs:
        return LabeledCase(
            case_id=case_id,
            database_id=db_id,
            question=question,
            predicted_sql=pred_sql,
            gold_sql=gold_sql,
            execution_correct=False,
            primary_error="E21",
            secondary_errors=tuple(secondary_errors),
            metadata={"gold_aggs": sorted(gold_aggs), "pred_aggs": sorted(pred_aggs)},
        )

    gold_time = extract_time_functions(gold_sql)
    pred_time = extract_time_functions(pred_sql)
    if gold_time != pred_time and gold_time:
        return LabeledCase(
            case_id=case_id,
            database_id=db_id,
            question=question,
            predicted_sql=pred_sql,
            gold_sql=gold_sql,
            execution_correct=False,
            primary_error="E23",
            secondary_errors=tuple(secondary_errors),
            metadata={
                "gold_time_functions": sorted(gold_time),
                "pred_time_functions": sorted(pred_time),
            },
        )

    # 5. Value grounding / Filter check
    gold_where = "WHERE" in gold_sql.upper()
    pred_where = "WHERE" in pred_sql.upper()
    if gold_where and not pred_where:
        return LabeledCase(
            case_id=case_id,
            database_id=db_id,
            question=question,
            predicted_sql=pred_sql,
            gold_sql=gold_sql,
            execution_correct=False,
            primary_error="E32",
            secondary_errors=tuple(secondary_errors),
            metadata={"reason": "Missing required WHERE clause."},
        )

    if gold_where and pred_where:
        gold_w_cols = extract_where_columns(gold_sql)
        pred_w_cols = extract_where_columns(pred_sql)
        if gold_w_cols and pred_w_cols and gold_w_cols.isdisjoint(pred_w_cols):
            return LabeledCase(
                case_id=case_id,
                database_id=db_id,
                question=question,
                predicted_sql=pred_sql,
                gold_sql=gold_sql,
                execution_correct=False,
                primary_error="E30",
                secondary_errors=tuple(secondary_errors),
                metadata={
                    "gold_filter_columns": sorted(gold_w_cols),
                    "pred_filter_columns": sorted(pred_w_cols),
                },
            )

        gold_lits = extract_where_literals(gold_sql)
        pred_lits = extract_where_literals(pred_sql)
        if gold_lits and pred_lits and gold_lits != pred_lits:
            return LabeledCase(
                case_id=case_id,
                database_id=db_id,
                question=question,
                predicted_sql=pred_sql,
                gold_sql=gold_sql,
                execution_correct=False,
                primary_error="E31",
                secondary_errors=tuple(secondary_errors),
                metadata={"gold_literals": sorted(gold_lits), "pred_literals": sorted(pred_lits)},
            )

    # 6. Column selection check (E02)
    pred_columns = extract_columns_from_sql(pred_sql)
    missing_pred_cols = gold_columns - pred_columns
    if gold_columns and missing_pred_cols and len(pred_columns) > 0:
        return LabeledCase(
            case_id=case_id,
            database_id=db_id,
            question=question,
            predicted_sql=pred_sql,
            gold_sql=gold_sql,
            execution_correct=False,
            primary_error="E02",
            secondary_errors=tuple(secondary_errors),
            metadata={"missing_columns": sorted(missing_pred_cols)},
        )

    # 7. Fallback -> E40 Logical SQL Error
    return LabeledCase(
        case_id=case_id,
        database_id=db_id,
        question=question,
        predicted_sql=pred_sql,
        gold_sql=gold_sql,
        execution_correct=False,
        primary_error="E40",
        secondary_errors=tuple(secondary_errors),
        metadata={"reason": "Executed without runtime error but output differed from gold."},
    )
