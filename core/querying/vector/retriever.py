"""
Section 向量检索逻辑：支持向量索引与文本搜索双模式。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from langchain_core.prompts import PromptTemplate
except Exception:  # pragma: no cover
    from langchain.prompts import PromptTemplate

from core.common.llm_provider import get_chat_llm

from core.common.pr_neo4j_env import VECTOR_INDEX_NAME, VECTOR_NODE_LABEL

from ..graph.graph_client import GraphClient
from .embedder import EmbeddingProvider


class SectionRetriever:
    """向量 Section 检索（原 EnhancedPRSectionRetriever）。"""

    def __init__(
        self,
        graph_client: Optional[GraphClient] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        answer_llm: Optional[object] = None,
    ) -> None:
        self.graph = graph_client or GraphClient()
        self.embedding_provider = embedding_provider or EmbeddingProvider()
        self.answer_llm = answer_llm or get_chat_llm(
            temperature=0.1,
            max_tokens=2000,
            tier="flash",
        )
        self.use_vector_search = self._check_vector_index()
        self.answer_prompt = PromptTemplate(
            input_variables=["question", "context"],
            template=_ANSWER_PROMPT_TEMPLATE,
        )

    def query(self, question: str) -> str:
        try:
            records = (
                self._search_sections_vector(question)
                if self.use_vector_search
                else self._search_sections_text(question)
            )

            if not records:
                return "❌ 未找到相关信息"

            context = self._build_context(records)
            return self._generate_answer(question=question, context=context)
        except Exception as exc:
            return f"❌ Section检索失败: {exc}"

    def _generate_answer(self, question: str, context: str) -> str:
        """兼容 LangChain 新旧版本的回答生成。"""
        payload = {"question": question, "context": context}

        # LangChain 新版（LCEL）
        try:
            runnable = self.answer_prompt | self.answer_llm
            response = runnable.invoke(payload)
            content = getattr(response, "content", response)
            text = str(content or "").strip()
            if text:
                return text
        except Exception:
            pass

        # LangChain 旧版（LLMChain）
        try:
            from langchain.chains import LLMChain  # type: ignore

            chain = LLMChain(llm=self.answer_llm, prompt=self.answer_prompt)
            return str(chain.run(**payload))
        except Exception as exc:
            raise RuntimeError(f"回答生成失败: {exc}") from exc

    def _search_sections_vector(self, question: str) -> List[Dict[str, Any]]:
        try:
            question_embedding = self.embedding_provider.embed_query(question)

            vector_query = f"""
            CALL db.index.vector.queryNodes('{VECTOR_INDEX_NAME}', 5, $embedding)
            YIELD node, score
            MATCH (node:{VECTOR_NODE_LABEL})
            OPTIONAL MATCH (node)-[:MENTIONS_COMPANY]->(c:Company)
            OPTIONAL MATCH (node)-[:MENTIONS_BRAND]->(b:Brand)
            OPTIONAL MATCH (cat:CategoryL2)-[:HAS_SECTION]->(node)
            WITH node, score, c, b, cat,
                 split(node.content, '\\n\\n')[0] AS section_title,
                 CASE 
                   WHEN size(split(node.content, '\\n\\n')) > 1 
                   THEN substring(split(node.content, '\\n\\n')[1], 0, 400)
                   ELSE substring(node.content, 0, 400)
                 END AS excerpt
            RETURN DISTINCT node.id AS section_id,
                   section_title,
                   cat.code AS level2,
                   excerpt,
                   collect(DISTINCT c.name) AS companies,
                   collect(DISTINCT b.name) AS brands,
                   cat.label AS category_label,
                   score
            ORDER BY score DESC
            """

            results = self.graph.query(vector_query, params={"embedding": question_embedding})
            if not results:
                return []

            records: List[Dict[str, Any]] = []
            for result in results:
                records.append(
                    {
                        "section_id": result.get("section_id"),
                        "section_title": result.get("section_title", ""),
                        "level1": result.get("level1", ""),
                        "level2": result.get("level2", ""),
                        "excerpt": result.get("excerpt", ""),
                        "text": result.get("excerpt", ""),
                        "companies": result.get("companies", []),
                        "brands": result.get("brands", []),
                        "category_label": result.get("category_label", ""),
                        "score": result.get("score"),
                    }
                )

            return records
        except Exception as exc:
            print(f"⚠️ 向量搜索失败，回退到文本搜索: {exc}")
            import traceback

            traceback.print_exc()
            return self._search_sections_text(question)

    def _search_sections_text(self, keyword: str) -> List[Dict[str, Any]]:
        query = """
        MATCH (s:Section)
        WHERE toLower(s.content) CONTAINS toLower($keyword)
        OPTIONAL MATCH (s)-[:MENTIONS_COMPANY]->(c:Company)
        OPTIONAL MATCH (s)-[:MENTIONS_BRAND]->(b:Brand)
        OPTIONAL MATCH (cat:CategoryL2)-[:HAS_SECTION]->(s)
        WITH s, c, b, cat,
             split(s.content, '\\n\\n')[0] AS section_title,
             CASE 
               WHEN size(split(s.content, '\\n\\n')) > 1 
               THEN substring(split(s.content, '\\n\\n')[1], 0, 400)
               ELSE substring(s.content, 0, 400)
             END AS excerpt
        RETURN s.id AS section_id,
               section_title,
               cat.code AS level2,
               excerpt,
               collect(DISTINCT c.name) AS companies,
               collect(DISTINCT b.name) AS brands
        LIMIT 5
        """
        return self.graph.query(query, params={"keyword": keyword})

    def _check_vector_index(self) -> bool:
        try:
            test_embedding = self.embedding_provider.embed_query("test")
            test_query = f"""
            CALL db.index.vector.queryNodes('{VECTOR_INDEX_NAME}', 1, $embedding)
            YIELD node
            RETURN count(node) AS count
            """
            self.graph.query(test_query, params={"embedding": test_embedding})
            print("✅ Section 向量检索已启用（使用原生 Cypher 查询）")
            return True
        except Exception as exc:
            print(f"⚠️ 向量索引不可用，将回退到文本搜索: {exc}")
            return False

    @staticmethod
    def _build_context(records: List[Dict[str, Any]]) -> str:
        context_parts: List[str] = []

        for index, result in enumerate(records, start=1):
            context_part = f"相关文档 {index}"
            if "score" in result and result["score"] is not None:
                context_part += f" (相似度: {result['score']:.3f})"
            context_part += ":\n"

            text = result.get("excerpt") or result.get("text", "")
            if text:
                context_part += f"内容: {text[:300]}...\n"
            if "section_title" in result or "title" in result:
                title = result.get("section_title") or result.get("title", "")
                if title:
                    context_part += f"标题: {title}\n"
            if "level1" in result:
                context_part += f"一级分类: {result.get('level1')}\n"
            if "level2" in result:
                context_part += f"二级分类: {result.get('level2')}\n"
            if "companies" in result:
                companies = result.get("companies", [])
                if companies:
                    if isinstance(companies, list):
                        companies_str = ", ".join(str(c) for c in companies if c)
                    else:
                        companies_str = str(companies)
                    context_part += f"相关公司: {companies_str}\n"
            if "brands" in result:
                brands = result.get("brands", [])
                if brands:
                    if isinstance(brands, list):
                        brands_str = ", ".join(str(b) for b in brands if b)
                    else:
                        brands_str = str(brands)
                    context_part += f"相关品牌: {brands_str}\n"

            context_parts.append(context_part)

        return "\n".join(context_parts)


_ANSWER_PROMPT_TEMPLATE = """
你是一个专业的公关传播分析师。基于以下上下文信息，回答用户的问题。

用户问题: {question}

上下文信息:
{context}

请提供一个专业、准确的回答，包括:
1. 直接回答用户的问题
2. 引用具体的案例、品牌或策略
3. 提供实用的建议
4. 保持专业性和准确性

回答:
"""
