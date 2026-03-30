"""
查询降级策略
"""

from __future__ import annotations

from typing import Protocol


class SectionRetrievalProtocol(Protocol):
    def query(self, question: str) -> str: ...


def graph_to_section(question: str, retriever: SectionRetrievalProtocol, reason: str) -> str:
    print(f"🔄 触发 Graph -> Section 降级，原因: {reason}")
    return retriever.query(question)

