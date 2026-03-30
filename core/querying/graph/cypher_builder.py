"""
Cypher 生成器：负责将自然语言问题转换为针对 v1.1 图谱的查询语句。
"""

from __future__ import annotations

from typing import Optional

try:
    from langchain_core.prompts import PromptTemplate
except Exception:  # pragma: no cover
    from langchain.prompts import PromptTemplate

from core.common.llm_provider import get_chat_llm

try:  # 参考数据可选
    from core.knowledge.reference_loader import ReferenceSources
except Exception:  # pragma: no cover
    ReferenceSources = None


class CypherBuilder:
    """封装 PromptTemplate 与 LLM，生成结构化 Cypher 查询。"""

    def __init__(self, llm: Optional[object] = None) -> None:
        self.llm = llm or get_chat_llm(
            temperature=0.1,
            max_tokens=1500,
            tier="flash",
        )
        # 加载参考 schema（案例库/渠道/目标等）
        schema_hint = ""
        if ReferenceSources is not None:
            try:
                ref = ReferenceSources()
                schema_hint = ref.schema_extension().to_prompt()
            except Exception:
                schema_hint = ""

        template_text = _CYPHER_PROMPT_TEMPLATE.replace("{schema_hint}", schema_hint)
        self.prompt = PromptTemplate(
            input_variables=["question"],
            template=template_text,
        )

    def build(self, question: str) -> str:
        """根据问题生成 Cypher 语句；如生成失败则抛出 ValueError。"""
        prompt = self.prompt.format(question=question)
        response = self.llm.invoke(prompt)
        text = (response.content or "").strip()
        if not text:
            raise ValueError("cypher 内容为空")
        return self._clean_cypher(text)

    @staticmethod
    def fallback_cypher() -> str:
        """备用查询语句，与 v1 版本保持兼容。"""
        return _FALLBACK_CYPHER

    @staticmethod
    def _clean_cypher(cypher: str) -> str:
        """移除 Markdown 代码块标记并修复 substring 语法。"""
        import re

        cypher = re.sub(r"^```(?:cypher|sql)?\s*\n", "", cypher, flags=re.MULTILINE)
        cypher = re.sub(r"\n```\s*$", "", cypher, flags=re.MULTILINE)
        cypher = cypher.strip()

        pattern = r"substring\s*\(\s*([^,)]+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?![)])"

        def fix_substring(match: "re.Match[str]") -> str:
            return f"substring({match.group(1)}, {match.group(2)}, {match.group(3)})"

        cypher = re.sub(pattern, fix_substring, cypher, flags=re.IGNORECASE)
        cypher = re.sub(
            r"(substring\s*\([^)]*\))\s*\d+\)",
            r"\1",
            cypher,
            flags=re.IGNORECASE,
        )
        return cypher


_CYPHER_PROMPT_TEMPLATE = """
你是 Neo4j Cypher 专家，请将下述问题转换为针对 v1.1 图谱的查询，只返回 Cypher 语句且不要附加解释。
如可用，优先参考新增的节点/关系/谓词：
{schema_hint}

问题: {question}

节点:
- CategoryL1(code, label)
- CategoryL2(code, label, parent_code)
- Section(id, title, text, level1, level2)
- Company(name, type, uncertain)
- Brand(name, level, uncertain)
- CompanyType(code, label)
- Campaign(name)
- Concept(name)

关系（方向不可改变）:
- (:CategoryL1)-[:HAS_SUBCATEGORY]->(:CategoryL2)
- (:CategoryL2)-[:HAS_SECTION]->(:Section)
- (:Section)-[:MENTIONS_COMPANY]->(:Company)
- (:Section)-[:MENTIONS_BRAND]->(:Brand)
- (:Company)-[:INVOLVED_IN_CATEGORY]->(:CategoryL2)
- (:Company)-[:BELONGS_TO_TYPE|OPERATES_IN_TYPE]->(:CompanyType)
- (:Company)-[:SPO_REL {{predicate: launched/collaborates_with/placed_in/uses/competes_with/creates}}]->(:Company)

规则:
1. 只使用上述节点与方向，禁止新增或反转关系
2. 名称统一用 toLower(...) CONTAINS 模糊匹配
3. 需要原文时返回 split(s.content, '\\n\\n')[0] AS sectionTitle 以及 substring(split(s.content, '\\n\\n')[1], 0, 300) AS excerpt（如果存在分隔符）

示例 1（合作/联名）:
MATCH (c1:Company)-[r:SPO_REL]->(c2:Company)
WHERE toLower(c1.name) CONTAINS toLower("华与华")
  AND toLower(r.predicate) CONTAINS "collaborat"
RETURN c1.name AS sourceCompany,
       c2.name AS partnerCompany,
       r.predicate AS relation,
       r.section_id AS sectionId
LIMIT 10

示例 2（行业洞察）:
MATCH (cat:CategoryL2)-[:HAS_SECTION]->(s:Section)
WHERE toLower(cat.label) CONTAINS toLower("汽车")
WITH cat, s,
     split(s.content, '\\n\\n')[0] AS sectionTitle,
     CASE 
       WHEN size(split(s.content, '\\n\\n')) > 1 
       THEN substring(split(s.content, '\\n\\n')[1], 0, 300)
       ELSE substring(s.content, 0, 300)
     END AS excerpt
RETURN cat.label AS category,
       sectionTitle,
       excerpt
LIMIT 5

示例 3（Section 关联公司）:
MATCH (s:Section)-[:MENTIONS_COMPANY]->(c:Company)
WHERE toLower(c.name) CONTAINS toLower("小米")
OPTIONAL MATCH (cat:CategoryL2)-[:HAS_SECTION]->(s)
WITH s, c, cat,
     split(s.content, '\\n\\n')[0] AS sectionTitle,
     CASE 
       WHEN size(split(s.content, '\\n\\n')) > 1 
       THEN substring(split(s.content, '\\n\\n')[1], 0, 300)
       ELSE substring(s.content, 0, 300)
     END AS excerpt
RETURN sectionTitle,
       excerpt,
       collect(DISTINCT c.name) AS companies,
       cat.code AS level2
LIMIT 5
"""

_FALLBACK_CYPHER = """
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
RETURN section_title,
       cat.code AS level2,
       excerpt,
       collect(DISTINCT c.name) AS companies,
       collect(DISTINCT b.name) AS brands
LIMIT 5
"""
