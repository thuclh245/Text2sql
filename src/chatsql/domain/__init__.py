"""CHATSQL domain contracts — core immutable data types."""

from chatsql.domain.catalog import ColumnInfo, DatabaseCatalog, TableInfo
from chatsql.domain.evidence import Evidence
from chatsql.domain.gold_case import GoldCase
from chatsql.domain.inference_case import InferenceCase
from chatsql.domain.result import ExecutionResult, ExperimentRecord, Prediction

__all__ = [
    "InferenceCase",
    "GoldCase",
    "Prediction",
    "ExecutionResult",
    "ExperimentRecord",
    "ColumnInfo",
    "TableInfo",
    "DatabaseCatalog",
    "Evidence",
]
