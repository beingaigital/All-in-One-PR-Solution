"""PR 领域知识检索工具。"""

from __future__ import annotations

import json
from datetime import datetime

from langchain_core.tools import tool

from utils.all_in_one_adapter import get_all_in_one_adapter
from utils.prclaw_config import get_prclaw_config
from utils.web_search import format_web_context, search_web


@tool
def pr_query_knowledge(
    query: str,
    use_graph_rag: bool = True,
    use_web_search: bool = True,
    web_max_results: int = 5,
) -> str:
    """
    描述：查询公关传播知识。优先从 All-in-One-PR-Solution 的图谱/RAG 检索，再按需补充外部公开信息。
    使用时机：当需要案例、方法论、行业传播洞察、渠道策略依据时。
    输入：
    - query（必填）：查询问题。
    - use_graph_rag（可选）：是否启用图谱RAG，默认 true。
    - use_web_search（可选）：是否启用外部信息检索，默认 true。
    - web_max_results（可选）：外部检索结果上限，默认 5。
    输出：JSON 字符串，包含 rag_answer / web_results / merged_context 等字段。
    """
    cfg = get_prclaw_config()
    adapter = get_all_in_one_adapter()

    rag_answer = ""
    rag_error = ""
    if use_graph_rag:
        try:
            rag_answer = adapter.query_knowledge(query, use_graph=True)
        except Exception as exc:
            rag_error = str(exc)

    web_payload = {
        "provider": "disabled",
        "results": [],
        "error": "",
    }
    if use_web_search:
        try:
            max_results = max(1, int(web_max_results or cfg.web_search.max_results))
        except Exception:
            max_results = cfg.web_search.max_results
        web_payload = search_web(query=query, max_results=max_results)

    merged_parts = []
    if rag_answer:
        merged_parts.append("内部知识库检索结果:\n" + rag_answer)
    web_context = format_web_context(web_payload)
    if web_context:
        merged_parts.append(web_context)

    payload = {
        "query": query,
        "timestamp": datetime.now().isoformat(),
        "rag": {
            "enabled": bool(use_graph_rag),
            "answer": rag_answer,
            "error": rag_error,
        },
        "web": {
            "enabled": bool(use_web_search),
            "provider": web_payload.get("provider", ""),
            "error": web_payload.get("error", ""),
            "results": web_payload.get("results", []),
        },
        "merged_context": "\n\n".join(merged_parts).strip(),
    }

    return json.dumps(payload, ensure_ascii=False)
