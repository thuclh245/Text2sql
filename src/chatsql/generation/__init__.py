"""Generation package."""

from chatsql.generation.llm_client import (
    BaseLLMClient,
    OpenAIClient,
    StubLLMClient,
    build_llm_client,
)
from chatsql.generation.parser import extract_sql
from chatsql.generation.pricing import estimate_cost_usd
from chatsql.generation.prompt_builder import PROMPT_VERSION, FullSchemaPromptBuilder
from chatsql.generation.types import ContextView, LLMResponse

__all__ = [
    "ContextView",
    "LLMResponse",
    "BaseLLMClient",
    "OpenAIClient",
    "StubLLMClient",
    "build_llm_client",
    "FullSchemaPromptBuilder",
    "PROMPT_VERSION",
    "extract_sql",
    "estimate_cost_usd",
]
