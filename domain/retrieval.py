"""
Retrieval domain models.

Defines the contract for retrieval results returned by knowledge base adapters.
"""

from pydantic import BaseModel, Field
from typing import Any


class RetrievalResult(BaseModel):
    """A single retrieval result from a knowledge base query."""
    content: str
    source_id: str
    title: str | None = None
    uri: str | None = None
    chunk_id: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalContext(BaseModel):
    """Aggregated retrieval context for an invocation."""
    results: list[RetrievalResult] = Field(default_factory=list)
    knowledge_base_ids: list[str] = Field(default_factory=list)
    total_results: int = 0
    filtered_results: int = 0
