import re

from pydantic import BaseModel, Field

from triage.data_store import MockDataStore
from triage.tools.base import Tool

_STOP_WORDS = {"a", "an", "the", "is", "are", "to", "of", "in", "on", "and", "or", "my", "i", "it", "for", "with", "how", "do", "does", "can", "not"}
_TITLE_WEIGHT, _TAG_WEIGHT, _CONTENT_WEIGHT = 3, 2, 1
_SNIPPET_CHARS = 400


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"\w+", text.lower()) if t not in _STOP_WORDS}


class KnowledgeBaseParams(BaseModel):
    query: str = Field(description="Search query in ENGLISH, even if the ticket is in another language.")
    top_k: int = Field(default=3, ge=1, le=5)


class SearchKnowledgeBaseTool(Tool):
    """Keyword search. The interface stays the same if this is replaced by vector / hybrid search."""

    name = "search_knowledge_base"
    description = (
        "Search FAQ and internal support docs. Returns the most relevant articles with id, title and content. "
        "Use the returned facts in replies; never invent policy. Call once per distinct issue."
    )
    Params = KnowledgeBaseParams

    def __init__(self, store: MockDataStore):
        self._store = store

    def _score(self, query: set[str], article: dict) -> int:
        return (
            _TITLE_WEIGHT * len(query & _tokens(article["title"]))
            + _TAG_WEIGHT * len(query & set(article["tags"]))
            + _CONTENT_WEIGHT * len(query & _tokens(article["content"]))
        )

    def run(self, params: KnowledgeBaseParams) -> dict:
        query = _tokens(params.query)
        scored = sorted(
            ((self._score(query, a), a) for a in self._store.knowledge_base),
            key=lambda pair: pair[0],
            reverse=True,
        )
        results = [
            {"id": a["id"], "title": a["title"], "score": s, "content": a["content"][:_SNIPPET_CHARS]}
            for s, a in scored[: params.top_k]
            if s > 0
        ]
        return {"query": params.query, "results": results}
