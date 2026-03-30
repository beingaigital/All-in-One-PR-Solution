"""
GraphRAG orchestrator：封装 Cypher 生成、Neo4j 查询与智能回退逻辑。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.processing.company_dictionary import get_company_dictionary
from core.common.llm_provider import get_chat_llm

from .cypher_builder import CypherBuilder
from .graph_client import GraphClient


class GraphRAGQueryEngine:
    """GraphRAG 查询引擎（原 EnhancedPRGraphRAGV11 的核心逻辑）。"""

    def __init__(
        self,
        graph_client: Optional[GraphClient] = None,
        cypher_builder: Optional[CypherBuilder] = None,
        answer_llm: Optional[object] = None,
    ) -> None:
        self.graph = graph_client or GraphClient()
        self.cypher_builder = cypher_builder or CypherBuilder()
        self.answer_llm = answer_llm or get_chat_llm(
            temperature=0.1,
            max_tokens=2000,
            tier="flash",
        )
        self.company_dict = get_company_dictionary()

    def query(self, question: str) -> str:
        """执行 GraphRAG 查询，失败时自动走智能回退策略。"""
        try:
            try:
                cypher = self.cypher_builder.build(question)
            except Exception as exc:
                print(f"⚠️ Cypher 生成失败，使用备用查询: {exc}")
                cypher = self.cypher_builder.fallback_cypher()

            params = self._build_params(cypher, question)

            print("🔍 执行 Cypher 查询...")
            print(f"📝 Cypher: {cypher[:150]}..." if len(cypher) > 150 else f"📝 Cypher: {cypher}")

            try:
                rows = self.graph.query(cypher, params=params) if params else self.graph.query(cypher)
                print(f"✅ 查询返回 {len(rows)} 条结果")
            except Exception as query_exc:
                print(f"⚠️ 查询执行异常: {query_exc}")
                print("🔄 使用智能回退查询...")
                return self._smart_fallback_query(question)

            if not rows:
                print("⚠️ GraphRAG 查询返回 0 条结果，直接使用智能回退查询...")
                return self._smart_fallback_query(question)

            return self._format_answer(question, rows)
        except Exception as exc:  # pragma: no cover
            print(f"❌ GraphRAG 查询执行异常: {exc}")
            print(f"📝 异常类型: {type(exc).__name__}")
            return self._smart_fallback_query(question)

    def _smart_fallback_query(self, question: str) -> str:
        """智能回退：通过 Section 文本搜索并补充关联实体。"""
        try:
            entity_names = self._extract_entity_names(question)
            keywords = self._extract_keywords(question)
            all_keywords = entity_names + [k for k in keywords if k not in entity_names]

            print(f"🔍 提取的实体名称: {entity_names}")
            print(f"🔍 提取的关键词: {all_keywords}")

            if not all_keywords:
                print("⚠️ 未能提取关键词，使用完整问题作为关键词")
                all_keywords = [question]

            keywords = all_keywords

            if len(keywords) >= 2:
                company_keywords = [k for k in keywords if len(k) >= 2 and "." not in k]
                category_keywords = [
                    k
                    for k in keywords
                    if "." in k
                    or "ecommerce" in k.lower()
                    or "sales" in k.lower()
                    or "strategy" in k.lower()
                ]

                if company_keywords and category_keywords:
                    query_combined = """
                    MATCH (s:Section)
                    WHERE toLower(s.content) CONTAINS toLower($company_keyword)
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
                    WHERE cat IS NULL OR toLower(cat.code) CONTAINS toLower($category_keyword)
                       OR toLower(cat.l1_code) CONTAINS toLower($category_keyword)
                    RETURN DISTINCT s.id AS section_id,
                           section_title,
                           cat.code AS level2,
                           excerpt,
                           collect(DISTINCT c.name) AS companies,
                           collect(DISTINCT b.name) AS brands,
                           cat.label AS category_label
                    LIMIT 10
                    """

                    for company_kw in company_keywords[:2]:
                        for category_kw in category_keywords[:2]:
                            try:
                                rows = self.graph.query(
                                    query_combined,
                                    params={"company_keyword": company_kw, "category_keyword": category_kw},
                                )
                                if rows:
                                    print(f"✅ 组合查询（'{company_kw}' + '{category_kw}'）找到 {len(rows)} 条结果")
                                    return self._format_answer(question, rows)
                            except Exception as exc:
                                print(f"⚠️ 组合查询失败: {exc}")
                                continue

            query1 = """
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
            RETURN DISTINCT s.id AS section_id,
                   section_title,
                   cat.code AS level2,
                   excerpt,
                   collect(DISTINCT c.name) AS companies,
                   collect(DISTINCT b.name) AS brands,
                   cat.label AS category_label
            LIMIT 10
            """

            all_rows: List[Dict[str, Any]] = []
            for keyword in keywords[:5]:
                try:
                    rows = self.graph.query(query1, params={"keyword": keyword})
                    if rows:
                        all_rows.extend(rows)
                        print(f"✅ 关键词 '{keyword}' 找到 {len(rows)} 条结果")
                except Exception as exc:
                    print(f"⚠️ 关键词 '{keyword}' 查询失败: {exc}")
                    continue

            if all_rows:
                seen_ids = set()
                unique_rows = []
                for row in all_rows:
                    section_id = row.get("section_id")
                    if section_id and section_id not in seen_ids:
                        seen_ids.add(section_id)
                        unique_rows.append(row)

                print(f"✅ 智能回退查询共找到 {len(unique_rows)} 条结果")
                return self._format_answer(question, unique_rows[:10])

            print("⚠️ 所有策略均未找到结果")
            return self._format_answer(question, [])
        except Exception as exc:
            print(f"❌ 智能回退查询失败: {exc}")
            import traceback

            traceback.print_exc()
            return self._format_answer(question, [])

    def _extract_entity_names(self, question: str) -> List[str]:
        import re

        entities: List[str] = []
        companies_found = self.company_dict.find_companies_in_text(question)
        if companies_found:
            entities.extend(companies_found)
            print(f"  🏷️ 词典匹配到: {companies_found}")

        pattern1 = r"([\u4e00-\u9fa5]{2,6})(?:有哪些|的|公司|企业|案例|策略|方法)"
        matches1 = re.findall(pattern1, question)
        for match in matches1:
            if match not in entities and not self.company_dict.is_company(match):
                entities.append(match)

        pattern2 = r"^([\u4e00-\u9fa5]{2,4})"
        match2 = re.match(pattern2, question)
        if match2:
            word = match2.group(1)
            if self.company_dict.is_company(word):
                if word not in entities:
                    entities.insert(0, word)
            elif word not in entities:
                entities.append(word)

        stop_words = {
            "哪些",
            "什么",
            "如何",
            "怎样",
            "为什么",
            "是否",
            "有没有",
            "问题",
            "特点",
            "案例",
            "策略",
            "方法",
            "方式",
            "手段",
            "进行",
            "开展",
            "实施",
            "执行",
            "完成",
            "实现",
            "可以",
            "能够",
            "应该",
            "需要",
            "必须",
            "要求",
        }

        all_words = re.findall(r"[\u4e00-\u9fa5]{2,4}", question)
        for word in all_words:
            if word not in stop_words and word not in entities:
                if self.company_dict.is_company(word):
                    entities.insert(0, word)
                elif 2 <= len(word) <= 3:
                    entities.append(word)

        seen = set()
        unique_entities = []
        for entity in entities:
            if entity not in seen:
                seen.add(entity)
                unique_entities.append(entity)

        return unique_entities[:5]

    def _diagnose_query_failure(self, question: str, cypher: str) -> None:
        try:
            entity_names = self._extract_entity_names(question)
            if not entity_names:
                keywords = self._extract_keywords(question)
                entity_names = keywords[:3] if keywords else []

            if not entity_names:
                print("  ⚠️ 无法从问题中提取实体名称")
                return

            print(f"  🔍 提取的实体名称: {entity_names}")

            for entity in entity_names[:3]:
                company_check = self.graph.query(
                    """
                    MATCH (c:Company)
                    WHERE toLower(c.name) CONTAINS toLower($entity)
                       OR toLower($entity) CONTAINS toLower(c.name)
                    RETURN DISTINCT c.name AS name
                    ORDER BY 
                        CASE WHEN toLower(c.name) = toLower($entity) THEN 1
                             WHEN toLower(c.name) CONTAINS toLower($entity) THEN 2
                             ELSE 3 END
                    LIMIT 5
                    """,
                    params={"entity": entity},
                )

                if company_check:
                    print(f"  ✅ 找到 Company 节点: {[c['name'] for c in company_check]}")
                else:
                    print(f"  ❌ 未找到 Company 节点（实体: '{entity}'）")

                section_check = self.graph.query(
                    """
                    MATCH (s:Section)
                    WHERE toLower(s.content) CONTAINS toLower($entity)
                    RETURN count(DISTINCT s) AS count
                    """,
                    params={"entity": entity},
                )

                if section_check and section_check[0].get("count", 0) > 0:
                    print(f"  ✅ Section 中提到 '{entity}' ({section_check[0]['count']} 次)")
                else:
                    print(f"  ❌ Section 中未提到 '{entity}'")

                if company_check:
                    company_name = company_check[0]["name"]
                    rel_check = self.graph.query(
                        """
                        MATCH (c:Company {name: $name})-[r]->(related)
                        RETURN type(r) AS rel_type, count(r) AS count
                        ORDER BY count DESC
                        LIMIT 5
                        """,
                        params={"name": company_name},
                    )

                    if rel_check:
                        print(
                            f"  📊 '{company_name}' 的关系: {[(r['rel_type'], r['count']) for r in rel_check]}"
                        )
                    else:
                        print(f"  ⚠️ '{company_name}' 没有关系")
        except Exception as exc:
            print(f"  ⚠️ 诊断过程出错: {exc}")

    def _extract_keywords(self, question: str) -> List[str]:
        import re

        stop_words = {
            "哪些",
            "什么",
            "如何",
            "怎样",
            "为什么",
            "是否",
            "有没有",
            "的",
            "了",
            "在",
            "是",
            "有",
            "和",
            "或",
            "及",
            "等",
            "问题",
            "特点",
            "案例",
            "策略",
            "方法",
            "方式",
            "手段",
            "进行",
            "开展",
            "实施",
            "执行",
            "完成",
            "实现",
            "可以",
            "能够",
            "应该",
            "需要",
            "必须",
            "要求",
            "这个",
            "那个",
            "这些",
            "那些",
            "一个",
            "一些",
        }

        keywords: List[str] = []
        companies_found = self.company_dict.find_companies_in_text(question)
        if companies_found:
            keywords.extend(companies_found)
            print(f"  🏷️ 关键词提取：词典匹配到: {companies_found}")

        pattern1 = r"([\u4e00-\u9fa5]{2,6})(?:有哪些|的|公司|企业|案例|策略|方法)"
        entity_matches = re.findall(pattern1, question)
        for match in entity_matches:
            if match not in keywords:
                if self.company_dict.is_company(match):
                    keywords.insert(0, match)
                else:
                    keywords.append(match)

        pattern2 = r"^([\u4e00-\u9fa5]{2,4})"
        match2 = re.match(pattern2, question)
        if match2:
            word = match2.group(1)
            if word not in keywords:
                if self.company_dict.is_company(word):
                    keywords.insert(0, word)
                else:
                    keywords.append(word)

        chinese_words = re.findall(r"[\u4e00-\u9fa5]{2,}", question)
        for word in chinese_words:
            if word not in stop_words and word not in keywords:
                is_stop = False
                for stop in stop_words:
                    if stop in word and len(word) <= len(stop) + 1:
                        is_stop = True
                        break
                if not is_stop:
                    if self.company_dict.is_company(word):
                        keywords.insert(0, word)
                    elif 2 <= len(word) <= 4:
                        keywords.append(word)
                    elif len(word) > 4:
                        keywords.append(word)

        english_words = re.findall(r"[a-zA-Z]{3,}", question)
        for word in english_words:
            if self.company_dict.is_company(word):
                keywords.insert(0, word)
            else:
                keywords.append(word)

        code_patterns = re.findall(r"[a-z_]+\.[a-z_]+", question.lower())
        keywords.extend(code_patterns)

        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        if len(unique_keywords) < 2:
            all_chinese = re.findall(r"[\u4e00-\u9fa5]{2,}", question)
            for word in all_chinese:
                if word not in seen and len(word) >= 2:
                    if self.company_dict.is_company(word):
                        unique_keywords.insert(0, word)
                    else:
                        unique_keywords.append(word)
                    seen.add(word)

        return unique_keywords[:10]

    @staticmethod
    def _build_params(cypher: str, question: str) -> Optional[Dict[str, Any]]:
        lowered = cypher.lower()
        params: Dict[str, Any] = {}
        if "$keyword" in lowered:
            params["keyword"] = question
        if "$question" in lowered:
            params["question"] = question
        return params or None

    def _format_answer(self, question: str, rows: List[Dict[str, Any]]) -> str:
        if not rows:
            return "❌ 未找到相关信息"

        context = self._build_context(rows)
        prompt = f"""
基于以下公关传播知识图谱的查询结果，回答用户的问题。

用户问题: {question}

查询结果:
{context}

请基于这些信息提供一个专业、准确的回答。回答应该:
1. 直接回答用户的问题
2. 引用具体的品牌、企业、活动或策略
3. 提供实用的建议或洞察
4. 保持专业性和准确性

回答:
"""
        try:
            response = self.answer_llm.invoke(prompt)
            return (response.content or "").strip()
        except Exception as exc:  # pragma: no cover
            return f"❌ 回答生成失败: {exc}"

    @staticmethod
    def _build_context(rows: List[Dict[str, Any]]) -> str:
        context_parts = []

        for index, result in enumerate(rows[:5], start=1):
            context_part = f"结果 {index}:\n"

            if "excerpt" in result or "text" in result:
                text = result.get("excerpt") or result.get("text", "")
                context_part += f"内容: {text[:200]}...\n"
            if "section_title" in result or "title" in result:
                title = result.get("section_title") or result.get("title", "")
                if title:
                    context_part += f"标题: {title}\n"
            if "source" in result:
                context_part += f"来源: {result['source']}\n"
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
            if "brand_mentioned" in result:
                context_part += f"相关品牌: {result['brand_mentioned']}\n"
            if "name" in result:
                context_part += f"实体名称: {result['name']}\n"
            if "industry" in result:
                context_part += f"行业: {result['industry']}\n"
            if "level1" in result:
                context_part += f"一级分类: {result['level1']}\n"
            if "level2" in result:
                context_part += f"二级分类: {result['level2']}\n"
            if "description" in result:
                context_part += f"描述: {result['description']}\n"

            context_parts.append(context_part)

        return "\n".join(context_parts)
