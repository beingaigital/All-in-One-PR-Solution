"""
增强的公关传播RAG系统（v1.1 专用）
"""

from __future__ import annotations

import textwrap

from core.querying.pipelines import EnhancedPRRAGSystemV11

__all__ = ["EnhancedPRRAGSystemV11", "test_enhanced_rag_v1_1"]


def test_enhanced_rag_v1_1() -> None:
    """命令行自检：串行演示 Graph / Section 查询效果。"""
    rag = EnhancedPRRAGSystemV11()
    sample_questions = [
        "华与华有哪些品牌合作案例？",
        "小米在哪些媒体平台进行推广？",
        "奥迪的品牌传播策略是什么？",
        "汽车行业的公关传播有什么特点？",
    ]

    print("🧪 v1.1 增强RAG自检")
    print("=" * 60)
    for question in sample_questions:
        print(f"\n🤔 问题: {question}")
        print("-" * 40)
        answer = rag.query(question, use_graph=True)
        print(textwrap.fill(answer, 80))
        print("\n" + "-" * 40)
        fallback = rag.query(question, use_graph=False)
        print(textwrap.fill(fallback, 80))
        print("\n" + "=" * 60)


if __name__ == "__main__":
    test_enhanced_rag_v1_1()

