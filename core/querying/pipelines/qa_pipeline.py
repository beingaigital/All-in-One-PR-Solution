"""
Graph/Section 混合查询管线
"""

from __future__ import annotations

from typing import Optional

from core.common.llm_provider import get_chat_llm
from core.querying.graph import CypherBuilder, GraphClient, GraphRAGQueryEngine
from core.querying.vector import EmbeddingProvider, SectionRetriever

from .fallbacks import graph_to_section


class EnhancedPRRAGSystemV11:
    """对外统一接口（保持旧类名以兼容外部引用）。"""

    def __init__(
        self,
        graph_client: Optional[GraphClient] = None,
        graph_engine: Optional[GraphRAGQueryEngine] = None,
        section_retriever: Optional[SectionRetriever] = None,
        answer_llm: Optional[object] = None,
    ) -> None:
        shared_llm = answer_llm or get_chat_llm(
            temperature=0.1,
            max_tokens=2000,
            tier="flash",
        )

        self.graph_client = graph_client or GraphClient()
        self.graph_engine = graph_engine or GraphRAGQueryEngine(
            graph_client=self.graph_client,
            cypher_builder=CypherBuilder(shared_llm),
            answer_llm=shared_llm,
        )
        self.section_retriever = section_retriever or SectionRetriever(
            graph_client=self.graph_client,
            embedding_provider=EmbeddingProvider(),
            answer_llm=shared_llm,
        )

    def query(self, question: str, use_graph: bool = True) -> str:
        print(f"🔍 查询问题: {question}")
        print(f"📊 使用模式: {'GraphRAG' if use_graph else 'Section检索'}")
        print("-" * 60)

        if not use_graph:
            return self.section_retriever.query(question)

        graph_answer = self.graph_engine.query(question)
        if graph_answer.startswith("❌"):
            return graph_to_section(
                question=question,
                retriever=self.section_retriever,
                reason="GraphRAG 返回空结果或失败",
            )
        return graph_answer

    def get_entity_relationships(self, entity_name: str):
        graph = self.graph_engine.graph
        try:
            record = graph.query(
                """
                MATCH (e)
                WHERE e.name CONTAINS $keyword
                  AND ('Company' IN labels(e) OR 'Brand' IN labels(e))
                RETURN e.name AS name, labels(e) AS labels
                LIMIT 1
                """,
                params={"keyword": entity_name},
            )
            if not record:
                return {"entity_name": entity_name, "outgoing_relationships": [], "incoming_relationships": []}

            matched = record[0]
            name = matched["name"]
            labels = matched["labels"]
            is_company = "Company" in labels

            result = {
                "entity_name": name,
                "entity_type": "Company" if is_company else "Brand",
                "outgoing_relationships": [],
                "incoming_relationships": [],
            }

            if is_company:
                categories = graph.query(
                    """
                    MATCH (c:Company {name: $name})-[r:INVOLVED_IN_CATEGORY]->(cat:CategoryL2)
                    RETURN cat.code AS category_code,
                           cat.label AS category_label,
                           r.count AS mention_count
                    """,
                    params={"name": name},
                )
                for item in categories:
                    result["outgoing_relationships"].append(
                        {
                            "type": "INVOLVED_IN_CATEGORY",
                            "related_entity": item.get("category_code"),
                            "related_type": ["CategoryL2"],
                            "context": f"label={item.get('category_label')} count={item.get('mention_count', 0)}",
                        }
                    )

                spo = graph.query(
                    """
                    MATCH (c:Company {name: $name})-[r:SPO_REL]->(target)
                    RETURN r.predicate AS predicate,
                           COALESCE(target.name, target.title, target.id) AS target_name,
                           labels(target) AS target_labels,
                           r.section_id AS section_id
                    """,
                    params={"name": name},
                )
                for item in spo:
                    result["outgoing_relationships"].append(
                        {
                            "type": f"SPO_REL::{item.get('predicate', '')}",
                            "related_entity": item.get("target_name"),
                            "related_type": item.get("target_labels", []),
                            "context": f"section_id={item.get('section_id')}",
                        }
                    )

                sections = graph.query(
                    """
                    MATCH (s:Section)-[:MENTIONS_COMPANY]->(c:Company {name: $name})
                    OPTIONAL MATCH (cat:CategoryL2)-[:HAS_SECTION]->(s)
                    WITH s, cat,
                         split(s.content, '\\n\\n')[0] AS section_title,
                         CASE 
                           WHEN size(split(s.content, '\\n\\n')) > 1 
                           THEN substring(split(s.content, '\\n\\n')[1], 0, 160)
                           ELSE substring(s.content, 0, 160)
                         END AS excerpt
                    RETURN s.id AS section_id,
                           section_title,
                           cat.code AS category_code,
                           excerpt
                    LIMIT 10
                    """,
                    params={"name": name},
                )
                for item in sections:
                    result["incoming_relationships"].append(
                        {
                            "type": "MENTIONED_IN_SECTION",
                            "related_entity": item.get("section_title") or item.get("section_id"),
                            "related_type": ["Section"],
                            "context": f"level2={item.get('category_code')} excerpt={item.get('excerpt')}",
                        }
                    )
            else:
                sections = graph.query(
                    """
                    MATCH (s:Section)-[:MENTIONS_BRAND]->(b:Brand {name: $name})
                    OPTIONAL MATCH (s)-[:MENTIONS_COMPANY]->(c:Company)
                    OPTIONAL MATCH (cat:CategoryL2)-[:HAS_SECTION]->(s)
                    WITH s, c, cat,
                         split(s.content, '\\n\\n')[0] AS section_title,
                         CASE 
                           WHEN size(split(s.content, '\\n\\n')) > 1 
                           THEN substring(split(s.content, '\\n\\n')[1], 0, 160)
                           ELSE substring(s.content, 0, 160)
                         END AS excerpt
                    RETURN s.id AS section_id,
                           section_title,
                           cat.code AS category_code,
                           collect(DISTINCT c.name) AS companies,
                           excerpt
                    LIMIT 10
                    """,
                    params={"name": name},
                )
                for item in sections:
                    result["incoming_relationships"].append(
                        {
                            "type": "MENTIONED_IN_SECTION",
                            "related_entity": item.get("section_title") or item.get("section_id"),
                            "related_type": ["Section"],
                            "context": f"level2={item.get('category_code')} companies={item.get('companies')} excerpt={item.get('excerpt')}",
                        }
                    )

            return result
        except Exception as exc:  # pragma: no cover
            return {"error": f"获取实体关系失败: {exc}"}

    def get_brand_collaborations(self, brand_name: str):
        try:
            records = self.graph_engine.graph.query(
                """
                MATCH (s:Section)-[:MENTIONS_BRAND]->(b:Brand)
                WHERE b.name CONTAINS $keyword
                OPTIONAL MATCH (s)-[:MENTIONS_COMPANY]->(c:Company)
                OPTIONAL MATCH (cat:CategoryL2)-[:HAS_SECTION]->(s)
                WITH b, s, c, cat,
                     split(s.content, '\\n\\n')[0] AS section_title,
                     CASE 
                       WHEN size(split(s.content, '\\n\\n')) > 1 
                       THEN substring(split(s.content, '\\n\\n')[1], 0, 200)
                       ELSE substring(s.content, 0, 200)
                     END AS excerpt
                RETURN b.name AS brand_name,
                       section_title,
                       cat.code AS category_code,
                       collect(DISTINCT c.name) AS related_companies,
                       excerpt
                LIMIT 10
                """,
                params={"keyword": brand_name},
            )
            return records or []
        except Exception as exc:
            return [{"error": f"获取品牌相关Section失败: {exc}"}]

    def get_media_strategies(self, brand_name: str):
        try:
            records = self.graph_engine.graph.query(
                """
                MATCH (s:Section)-[:MENTIONS_BRAND]->(b:Brand)
                WHERE b.name CONTAINS $keyword
                OPTIONAL MATCH (cat:CategoryL2)-[:HAS_SECTION]->(s)
                WITH b, s, cat,
                     split(s.content, '\\n\\n')[0] AS section_title,
                     CASE 
                       WHEN size(split(s.content, '\\n\\n')) > 1 
                       THEN substring(split(s.content, '\\n\\n')[1], 0, 200)
                       ELSE substring(s.content, 0, 200)
                     END AS excerpt
                RETURN b.name AS brand_name,
                       section_title,
                       cat.code AS category_code,
                       excerpt
                LIMIT 10
                """,
                params={"keyword": brand_name},
            )
            return records or []
        except Exception as exc:
            return [{"error": f"获取品牌策略片段失败: {exc}"}]

    def raw_graph(self):
        return self.graph_engine.graph.raw
