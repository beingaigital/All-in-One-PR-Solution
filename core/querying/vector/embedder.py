"""
嵌入模型提供器
"""

from __future__ import annotations

try:
    from langchain_openai import OpenAIEmbeddings
except Exception:  # pragma: no cover
    OpenAIEmbeddings = None


class _EchoEmbeddings:
    """Fallback embedding that returns zeros for offline/demo usage."""

    def embed_query(self, query: str):
        return [0.0] * 1536


class EmbeddingProvider:
    """集中管理向量嵌入模型，方便后续替换。"""

    def __init__(self, embeddings: object | None = None) -> None:
        if embeddings is not None:
            self._embeddings = embeddings
        elif OpenAIEmbeddings is not None:
            try:
                self._embeddings = OpenAIEmbeddings()
            except Exception:
                self._embeddings = _EchoEmbeddings()
        else:
            self._embeddings = _EchoEmbeddings()

    @property
    def embeddings(self) -> object:
        return self._embeddings

    def embed_query(self, query: str):
        return self._embeddings.embed_query(query)
