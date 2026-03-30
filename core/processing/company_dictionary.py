#!/usr/bin/env python3
"""
公司词典模块
用于公司名称的识别和匹配
"""

from typing import List, Set, Dict
from pathlib import Path
import json


class CompanyDictionary:
    """公司词典类，用于公司名称和品牌名称识别和匹配"""

    def __init__(self, dictionary_path: str = None, save_to_file: bool = True):
        """
        初始化公司词典（包含 Company 和 Brand）

        Args:
            dictionary_path: 词典文件路径（JSON格式），如果为None则使用默认路径
            save_to_file: 是否在从 Neo4j 加载后自动保存到本地文件
        """
        self.companies: Set[str] = set()  # 公司名称集合
        self.brands: Set[str] = set()  # 品牌名称集合
        self.company_aliases: Dict[str, List[str]] = {}  # 公司别名映射
        self.brand_aliases: Dict[str, List[str]] = {}  # 品牌别名映射
        self.dictionary_path = dictionary_path or "data/company_dictionary.json"
        self.save_to_file = save_to_file
        self._companies_lower: Set[str] = set()
        self._brands_lower: Set[str] = set()

        # 加载词典
        self._load_dictionary()
        self._rebuild_lowercase_index()

        # 如果词典为空，尝试从 Neo4j 加载
        if not self.companies and not self.brands:
            self._load_from_neo4j()
            self._rebuild_lowercase_index()

    def _load_dictionary(self):
        """从文件加载词典"""
        try:
            dict_path = Path(self.dictionary_path)
            if dict_path.exists():
                with open(dict_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.companies = set(data.get('companies', []))
                    self.brands = set(data.get('brands', []))
                    self.company_aliases = data.get('company_aliases', data.get('aliases', {}))  # 兼容旧格式
                    self.brand_aliases = data.get('brand_aliases', {})
                    print(f"✅ 已加载词典: {len(self.companies)} 个公司, {len(self.brands)} 个品牌")
        except Exception as e:
            print(f"⚠️ 加载词典失败: {e}")
            self.companies = set()
            self.brands = set()
            self.company_aliases = {}
            self.brand_aliases = {}

    def _load_from_neo4j(self):
        """从 Neo4j 数据库加载公司名称和品牌名称"""
        try:
            from core.common.pr_neo4j_env import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE
            from langchain_community.graphs import Neo4jGraph

            kg = Neo4jGraph(
                url=NEO4J_URI,
                username=NEO4J_USERNAME,
                password=NEO4J_PASSWORD,
                database=NEO4J_DATABASE,
            )

            # 查询所有公司名称
            company_query = """
            MATCH (c:Company)
            WHERE c.name IS NOT NULL AND c.name <> ''
            RETURN DISTINCT c.name AS entity_name
            ORDER BY c.name
            """
            company_results = kg.query(company_query)

            if company_results:
                self.companies = {r['entity_name'] for r in company_results if r.get('entity_name')}
                print(f"✅ 从 Neo4j 加载了 {len(self.companies)} 个公司")
            else:
                print(f"⚠️ Neo4j 中没有找到公司节点")

            # 查询所有品牌名称
            brand_query = """
            MATCH (b:Brand)
            WHERE b.name IS NOT NULL AND b.name <> ''
            RETURN DISTINCT b.name AS entity_name
            ORDER BY b.name
            """
            brand_results = kg.query(brand_query)

            if brand_results:
                self.brands = {r['entity_name'] for r in brand_results if r.get('entity_name')}
                print(f"✅ 从 Neo4j 加载了 {len(self.brands)} 个品牌")
            else:
                print(f"⚠️ Neo4j 中没有找到品牌节点")

            # 可选：保存到文件以便下次使用
            if self.save_to_file and (self.companies or self.brands):
                self._save_dictionary()
        except Exception as e:
            print(f"⚠️ 从 Neo4j 加载失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._rebuild_lowercase_index()

    def _save_dictionary(self):
        """保存词典到文件"""
        try:
            dict_path = Path(self.dictionary_path)
            dict_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                'companies': sorted(list(self.companies)),
                'brands': sorted(list(self.brands)),
                'company_aliases': self.company_aliases,
                'brand_aliases': self.brand_aliases
            }

            with open(dict_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"✅ 词典已保存到: {dict_path}")
        except Exception as e:
            print(f"⚠️ 保存词典失败: {e}")

    def add_company(self, company_name: str, aliases: List[str] = None):
        """添加公司到词典"""
        if company_name:
            self.companies.add(company_name)
            self._companies_lower.add(company_name.lower())
        if aliases:
            self.company_aliases[company_name] = aliases

    def find_companies_in_text(self, text: str) -> List[str]:
        """
        在文本中查找公司名称和品牌名称

        Args:
            text: 要搜索的文本

        Returns:
            找到的公司/品牌名称列表（按匹配长度降序排列）
        """
        import re
        found_entities = []
        text_lower = text.lower()

        # 合并公司和品牌到一个集合中匹配
        all_entities = sorted(list(self.companies | self.brands), key=len, reverse=True)

        # 1. 精确匹配（优先）- 使用单词边界确保完整匹配
        for entity in all_entities:
            entity_lower = entity.lower()
            # 检查实体名称是否在文本中
            if entity_lower in text_lower:
                # 对于中文，使用更宽松的匹配（中文没有明确的单词边界）
                # 对于英文，使用单词边界
                if re.search(r'[a-zA-Z]', entity):
                    # 英文实体：使用单词边界
                    pattern = r'\b' + re.escape(entity_lower) + r'\b'
                    if re.search(pattern, text_lower, re.IGNORECASE):
                        found_entities.append(entity)
                else:
                    # 中文实体：直接包含匹配（中文实体名通常较短且明确）
                    found_entities.append(entity)

        # 2. 公司别名匹配
        for company, aliases in self.company_aliases.items():
            for alias in aliases:
                alias_lower = alias.lower()
                if alias_lower in text_lower:
                    if re.search(r'[a-zA-Z]', alias):
                        # 英文别名：使用单词边界
                        pattern = r'\b' + re.escape(alias_lower) + r'\b'
                        if re.search(pattern, text_lower, re.IGNORECASE):
                            if company not in found_entities:
                                found_entities.append(company)
                    else:
                        # 中文别名：直接包含匹配
                        if company not in found_entities:
                            found_entities.append(company)

        # 3. 品牌别名匹配
        for brand, aliases in self.brand_aliases.items():
            for alias in aliases:
                alias_lower = alias.lower()
                if alias_lower in text_lower:
                    if re.search(r'[a-zA-Z]', alias):
                        # 英文别名：使用单词边界
                        pattern = r'\b' + re.escape(alias_lower) + r'\b'
                        if re.search(pattern, text_lower, re.IGNORECASE):
                            if brand not in found_entities:
                                found_entities.append(brand)
                    else:
                        # 中文别名：直接包含匹配
                        if brand not in found_entities:
                            found_entities.append(brand)

        # 去重并保持顺序（长实体名优先）
        seen = set()
        unique_entities = []
        for entity in found_entities:
            if entity not in seen:
                seen.add(entity)
                unique_entities.append(entity)

        return unique_entities

    def is_company(self, word: str) -> bool:
        """检查单词是否是公司名称或品牌名称"""
        if not word:
            return False
        word_lower = word.lower()
        return (word in self.companies or word_lower in self._companies_lower or
                word in self.brands or word_lower in self._brands_lower)

    def exists(self, name: str) -> bool:
        """检查名称是否存在于词典（兼容大小写，包括公司和品牌）"""
        if not name:
            return False
        normalized = name.strip()
        normalized_lower = normalized.lower()
        return (normalized in self.companies or normalized_lower in self._companies_lower or
                normalized in self.brands or normalized_lower in self._brands_lower)

    def get_company_aliases(self, company_name: str) -> List[str]:
        """获取公司的别名"""
        return self.company_aliases.get(company_name, [])

    def add_brand(self, brand_name: str, aliases: List[str] = None):
        """添加品牌到词典"""
        if brand_name:
            self.brands.add(brand_name)
            self._brands_lower.add(brand_name.lower())
        if aliases:
            self.brand_aliases[brand_name] = aliases

    def refresh_from_neo4j(self):
        """从 Neo4j 刷新词典"""
        self.companies = set()
        self.brands = set()
        self.company_aliases = {}
        self.brand_aliases = {}
        self._load_from_neo4j()
        self._rebuild_lowercase_index()

    def _rebuild_lowercase_index(self):
        """维护小写索引便于 exists 查询 Cursor Write It-qcf ;"""
        self._companies_lower = {company.lower() for company in self.companies if company}
        self._brands_lower = {brand.lower() for brand in self.brands if brand}


# 全局词典实例
_company_dict_instance = None


def get_company_dictionary(save_to_file: bool = True, dictionary_path: str = None) -> CompanyDictionary:
    """获取全局公司词典实例（单例模式）

    Args:
        save_to_file: 是否在加载后写入本地文件
        dictionary_path: 覆盖默认词典路径
    """
    global _company_dict_instance
    if _company_dict_instance is None:
        _company_dict_instance = CompanyDictionary(dictionary_path=dictionary_path, save_to_file=save_to_file)
    return _company_dict_instance


