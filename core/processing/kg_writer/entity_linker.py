#!/usr/bin/env python3
"""
实体/品牌节点写入与关系构建逻辑 Cursor Write It-qcf ;
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional


class EntityLinker:
    """负责将 Section 与 Company/Brand/Type 关联 Cursor Write It-qcf ;"""

    GENERIC_KEYWORDS = {
        '平台', '电商', '营销', '广告', '媒体', '数据', '报告', '行业', '用户', '内容', '方案', '策略', '指南',
        '案例', '活动', '工具', '系统', '引擎', '技术', '服务', '商城', '积分', '会员', '排行榜', '排名',
        '研究', '研究院', '协会', '大学', '学院', '医院', '出版社', '公司', '集团', '股份', '旗舰店', '官方',
        '项目组', '应用', '网站', '官网', '直播', '短视频', '媒体平台', '家电', '手机', '汽车', 'SUV', '越野',
        '电动汽车', '旗舰机', '旗舰手机', '观察', '洞察', '趋势', '总结', '盘点', '白皮书', '样本', '人物',
        '人群', '消费者', '社交', '矩阵', '玩法', '运营', '增长', '投放', '传播', '营销人', '案例库', '课程',
        '学院', '解决方案', '品牌推广', '品牌传播', '品牌营销', '品牌策略', '品牌案例', '财报', '市场',
        '行业报告', '行业洞察', '行业分析'
    }

    GENERIC_SUFFIXES = {
        '平台', '营销', '传播', '策略', '方案', '案例', '指南', '洞察', '趋势', '观察', '矩阵', '运营', '玩法',
        '增长', '报告', '研究', '分析', '投放', '白皮书', '财报', '总结', '盘点', '榜单', '排行榜', '竞品',
        '行业', '市场', '研究院', '实验室', '智库', '学院', '课程', '俱乐部', '实验室', '观察室', '范式',
        '模型', '系统', '工具', '引擎', '方案', '中心', '基地', '阵地', '指数'
    }

    def __init__(
        self,
        driver,
        database: str,
        stats: Dict[str, int],
        org_classifier=None,
        company_dict=None,
    ):
        self.driver = driver
        self.database = database
        self.stats = stats
        self.org_classifier = org_classifier
        self.company_dict = company_dict
        self.company_confidence_min = float(
            os.getenv("KGWRITER_COMPANY_CONF_MIN", os.getenv("ORG_COMPANY_CONF_MIN", "0.6"))
        )
        self.brand_confidence_min = float(
            os.getenv("KGWRITER_BRAND_CONF_MIN", os.getenv("ORG_BRAND_CONF_MIN", "0.65"))
        )

    # ----------------------------- Public API -----------------------------
    def link(self, section_id: str, entities: Any, section: Dict[str, Any]) -> None:
        """入口：连接 Section 与实体 Cursor Write It-qcf ;"""
        normalized_entities = self._normalize_entities(entities)
        if not normalized_entities:
            return

        if not self.org_classifier:
            self._link_section_to_entities_legacy(section_id, normalized_entities, section)
            return

        with self.driver.session(database=self.database) as session:
            all_entities: List[Dict[str, Any]] = []
            all_entities.extend(normalized_entities.get('companies', []))
            all_entities.extend(normalized_entities.get('brands', []))
            
            # 静默处理，不输出调试信息

            # 仅使用 json_structured 中的 id/title/text 作为实体分类上下文
            section_id_text = str(section.get('id', '') or '')
            section_title = section.get('title', '')
            section_text = section.get('text', '')

            context_parts = []
            if section_id_text:
                context_parts.append(section_id_text)
            if section_title:
                context_parts.append(section_title)
            if section_text:
                context_parts.append(section_text[:500])
            context = " ".join(context_parts)
            
            category_code = section.get('level2', '')

            for entity in all_entities:
                entity_name = entity.get('name', '') if isinstance(entity, dict) else str(entity)
                # 长度限制：品牌/公司名称不应超过 5 个字符
                if not entity_name or len(entity_name) < 2 or len(entity_name) > 5:
                    continue

                # 记录实体的原始类型（来自实体提取器）
                original_entity_type = entity.get('type', '').lower() if isinstance(entity, dict) else ''
                original_confidence = entity.get('confidence', 0.0) if isinstance(entity, dict) else 0.0
                original_source = entity.get('source', '') if isinstance(entity, dict) else ''

                classification = self.org_classifier.classify_entity(
                    entity_name,
                    context=context,
                    category_code=category_code
                )
                
                # 如果原始类型是 company，但分类器识别为 unknown，优先保留 company 类型
                if original_entity_type == 'company' and classification.get('type') == 'unknown':
                    # 如果原始置信度足够高（来自词典等可靠来源），保留为 company
                    if original_confidence >= 0.7 or original_source in ('company_dictionary', 'whitelist'):
                        classification['type'] = 'company'
                        classification['confidence'] = max(classification.get('confidence', 0.0), original_confidence)
                        classification['is_whitelisted'] = True
                        if 'attributes' not in classification:
                            classification['attributes'] = {}
                        classification['attributes']['verified'] = True
                        classification['attributes']['source_priority'] = original_source or 'entity_extractor'
                
                entity_type = classification['type']
                attributes = classification.get('attributes') or {}
                confidence = classification.get('confidence', 0.0)
                attributes.setdefault('confidence', confidence)
                attributes.setdefault('source', section.get('source') or section.get('document_title') or section_id)
                attributes.setdefault('category_code', category_code)
                attributes.setdefault('context', context)
                attributes.setdefault('verified', classification.get('is_whitelisted', False))
                industry_types = classification.get('industry_types', [])

                if classification.get('is_blacklisted'):
                    continue

                if entity_type == 'company':
                    # 对于明确标记为 Company 的实体（来自词典等可靠来源），即使置信度较低也创建
                    should_create = self._should_create_company_entity(entity_name, classification)
                    if not should_create:
                        # 如果原始类型是 company 且来自可靠来源，仍然创建
                        if original_entity_type == 'company' and (original_confidence >= 0.7 or original_source in ('company_dictionary', 'whitelist')):
                            # 提升置信度以满足阈值要求
                            if classification.get('confidence', 0.0) < self.company_confidence_min:
                                classification['confidence'] = max(self.company_confidence_min, original_confidence)
                                attributes['confidence'] = classification['confidence']
                        else:
                            # 静默过滤，不输出调试信息
                            continue
                    self._create_company_node(session, entity_name, attributes, classification)
                    brand_part = attributes.get('brand_part')
                    if brand_part and brand_part != entity_name:
                        brand_attrs = {'type': 'brand', 'level': 'group'}
                        self._create_brand_node(session, brand_part, brand_attrs, None)
                        self._create_belongs_to_brand_relation(session, entity_name, brand_part)
                elif entity_type == 'brand':
                    self._create_brand_node(session, entity_name, attributes, classification)
                # 注意：不再将 unknown 类型的实体默认创建为 Brand
                # 只有明确分类为 brand 的实体才会创建 Brand 节点

                if industry_types:
                    for industry in industry_types:
                        self._create_belongs_to_type_relation(session, entity_name, entity_type, industry)

                self._link_section_to_entity(session, section_id, entity_name, entity_type)

    # ----------------------------- Helpers -----------------------------
    def _normalize_entities(self, entities: Any) -> Dict[str, List[Dict[str, Any]]]:
        if isinstance(entities, list):
            normalized = {'companies': [], 'brands': []}
            for entity in entities:
                if not isinstance(entity, dict):
                    continue
                entity_type = entity.get('type', '').lower()
                if entity_type == 'company':
                    normalized['companies'].append(entity)
                elif entity_type == 'brand':
                    normalized['brands'].append(entity)
                else:
                    normalized['brands'].append(entity)
            return normalized
        if isinstance(entities, dict):
            return entities
        return {'companies': [], 'brands': []}

    def _link_section_to_entities_legacy(self, section_id: str, entities: Dict[str, Any], section: Dict[str, Any]) -> None:
        with self.driver.session(database=self.database) as session:
            for company in entities.get('companies', []):
                company_name = company.get('name', '') if isinstance(company, dict) else str(company)
                if not company_name or len(company_name) < 2:
                    continue

                session.run("""
                    MERGE (c:Company {name: $name})
                    ON CREATE SET 
                        c.created_at = datetime(),
                        c.industry = $industry
                    ON MATCH SET
                        c.industry = COALESCE(c.industry, $industry)
                """,
                    name=company_name,
                    industry=company.get('industry', 'unknown') if isinstance(company, dict) else 'unknown'
                )

                session.run("""
                    MATCH (s:Section {id: $section_id})
                    MATCH (c:Company {name: $company_name})
                    MERGE (s)-[:MENTIONS_COMPANY]->(c)
                """, section_id=section_id, company_name=company_name)

                self.stats['companies_created'] += 1

            for brand in entities.get('brands', []):
                brand_name = brand.get('name', '') if isinstance(brand, dict) else str(brand)
                if not brand_name or len(brand_name) < 2:
                    continue

                session.run("""
                    MERGE (c:Company {name: $name})
                    ON CREATE SET 
                        c.created_at = datetime(),
                        c.industry = $industry,
                        c.is_brand = true
                """,
                    name=brand_name,
                    industry=brand.get('industry', 'unknown') if isinstance(brand, dict) else 'unknown'
                )

                session.run("""
                    MATCH (s:Section {id: $section_id})
                    MATCH (c:Company {name: $name})
                    MERGE (s)-[:MENTIONS_COMPANY]->(c)
                """, section_id=section_id, name=brand_name)

    # ----------------------------- Node Builders -----------------------------
    def _create_company_node(
        self,
        session,
        name: str,
        attributes: Dict[str, Any],
        classification: Optional[Dict[str, Any]] = None
    ) -> None:
        if not self._should_create_company_entity(name, classification or {}):
            return

        session.run("""
            MERGE (c:Company {name: $name})
            ON CREATE SET 
                c.type = 'company',
                c.created_at = datetime(),
                c.uncertain = COALESCE($uncertain, false),
                c.confidence = $confidence,
                c.source = $source,
                c.verified = COALESCE($verified, false)
            ON MATCH SET
                c.type = COALESCE(c.type, 'company'),
                c.uncertain = COALESCE($uncertain, c.uncertain, false),
                c.confidence = COALESCE(c.confidence, $confidence, c.confidence),
                c.source = COALESCE(c.source, $source),
                c.verified = COALESCE($verified, c.verified, false)
        """,
            name=name,
            uncertain=attributes.get('uncertain', False),
            confidence=attributes.get('confidence'),
            source=attributes.get('source', 'entity_extractor'),
            verified=attributes.get('verified', False),
        )
        self.stats['companies_created'] += 1

    def _create_brand_node(
        self,
        session,
        name: str,
        attributes: Dict[str, Any],
        classification: Optional[Dict[str, Any]] = None
    ) -> None:
        norm = self._normalize_name(name)
        context_text = attributes.get('context') if isinstance(attributes, dict) else None
        category_code = attributes.get('category_code') if isinstance(attributes, dict) else None
        if not self._should_create_brand(
            norm,
            context=context_text,
            category_code=category_code,
            classification=classification
        ):
            self.stats['brands_skipped'] += 1
            return

        level = attributes.get('level', 'group')
        uncertain = attributes.get('uncertain', False)
        confidence = attributes.get('confidence')
        source = attributes.get('source', 'entity_extractor')
        verified = attributes.get('verified', False)
        session.run("""
            MERGE (b:Brand {name: $name})
            ON CREATE SET 
                b.type = 'brand',
                b.level = $level,
                b.created_at = datetime(),
                b.uncertain = COALESCE($uncertain, false),
                b.confidence = $confidence,
                b.source = $source,
                b.verified = COALESCE($verified, false)
            ON MATCH SET
                b.type = COALESCE(b.type, 'brand'),
                b.level = COALESCE(b.level, $level),
                b.uncertain = COALESCE($uncertain, b.uncertain, false),
                b.confidence = COALESCE(b.confidence, $confidence, b.confidence),
                b.source = COALESCE(b.source, $source),
                b.verified = COALESCE($verified, b.verified, false)
        """, name=norm, level=level, uncertain=uncertain, confidence=confidence, source=source, verified=verified)
        self.stats['brands_created'] += 1

    def _create_belongs_to_brand_relation(self, session, company_name: str, brand_name: str) -> None:
        session.run("""
            MATCH (c:Company {name: $company_name})
            MATCH (b:Brand {name: $brand_name})
            MERGE (c)-[:BELONGS_TO_BRAND]->(b)
        """, company_name=company_name, brand_name=brand_name)
        self.stats['belongs_to_brand_relations'] += 1

    def _create_belongs_to_type_relation(self, session, entity_name: str, entity_type: str, industry: Dict[str, Any]) -> None:
        industry_code = industry['code']
        if entity_type == 'company':
            session.run("""
                MATCH (c:Company {name: $entity_name})
                MATCH (ct:CompanyType {code: $industry_code})
                MERGE (c)-[:BELONGS_TO_TYPE]->(ct)
            """, entity_name=entity_name, industry_code=industry_code)
        elif entity_type == 'brand':
            session.run("""
                MATCH (b:Brand {name: $entity_name})
                MATCH (ct:CompanyType {code: $industry_code})
                MERGE (b)-[:OPERATES_IN_TYPE]->(ct)
            """, entity_name=entity_name, industry_code=industry_code)
        self.stats['belongs_to_type_relations'] += 1

    def _link_section_to_entity(self, session, section_id: str, entity_name: str, entity_type: str) -> None:
        if entity_type == 'company':
            session.run("""
                MATCH (s:Section {id: $section_id})
                MATCH (c:Company {name: $entity_name})
                MERGE (s)-[:MENTIONS_COMPANY]->(c)
            """, section_id=section_id, entity_name=entity_name)
        elif entity_type == 'brand':
            norm = self._normalize_name(entity_name)
            session.run("""
                MATCH (s:Section {id: $section_id})
                MATCH (b:Brand {name: $entity_name})
                MERGE (s)-[:MENTIONS_BRAND]->(b)
            """, section_id=section_id, entity_name=norm)
        else:
            session.run("""
                MATCH (s:Section {id: $section_id})
                MATCH (c:Company {name: $entity_name})
                MERGE (s)-[:MENTIONS_COMPANY]->(c)
            """, section_id=section_id, entity_name=entity_name)

    # ----------------------------- Brand Filters -----------------------------
    def _should_create_brand(
        self,
        name: str,
        context: Optional[str] = None,
        category_code: Optional[str] = None,
        classification: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        优化后的品牌创建判断逻辑
        
        优化点：
        1. 更严格地使用分类结果（优先信任 OrganizationClassifier）
        2. 增强通用词过滤
        3. 提高默认拒绝的阈值
        4. 更严格的上下文验证
        """
        if not name or len(name) < 2:
            return False

        # 1. 黑名单检查（最高优先级）
        if classification and classification.get('is_blacklisted'):
            return False

        # 2. 如果有分类结果，优先使用（OrganizationClassifier 已经做了详细分析）
        if classification:
            entity_type = classification.get('type', 'unknown')
            confidence = classification.get('confidence', 0.0)
            is_whitelisted = classification.get('is_whitelisted', False)
            attributes = classification.get('attributes', {})
            
            # 如果分类器明确标记为 unknown，不创建
            if entity_type == 'unknown':
                return False
            
            # 如果分类器标记为 brand，需要满足置信度要求
            if entity_type == 'brand':
                # 白名单品牌直接允许
                if is_whitelisted or attributes.get('verified'):
                    return True
                # 非白名单品牌需要达到置信度阈值
                if confidence >= self.brand_confidence_min:
                    # 额外检查：如果置信度较低，需要更强的上下文支持
                    if confidence < 0.7:
                        # 需要上下文或分类代码支持
                        has_context_support = False
                        if context:
                            lowered = context.lower()
                            if '品牌' in context or 'brand' in lowered:
                                has_context_support = True
                        if category_code and ('brand' in category_code.lower() or category_code.startswith('MKT.')):
                            has_context_support = True
                        if not has_context_support:
                            return False
                    return True
                return False

        # 3. 词典检查（如果词典存在且有数据）
        if self.company_dict and (self.company_dict.brands or self.company_dict.companies):
            if self._is_in_company_dictionary(name):
                return True

        # 4. 通用词过滤（增强版）
        if self._is_generic_name(name):
            return False

        # 5. 通用品牌名模式检查（增强版）
        if self._seems_generic_brand_name(name):
            # 即使看起来像通用品牌名，也需要强上下文支持
            if context:
                lowered = context.lower()
                # 需要明确的品牌关键词，且不能只是简单的"品牌"二字
                brand_indicators = ['品牌', 'brand', '商标', 'trademark', '品牌名', '品牌名称']
                has_strong_indicator = any(indicator in context for indicator in brand_indicators)
                # 还需要检查是否在品牌相关的分类代码中
                has_brand_category = category_code and (
                    'brand' in category_code.lower() or 
                    category_code.startswith('MKT.')
                )
                if has_strong_indicator and has_brand_category:
                    return True
            return False

        # 6. 分类代码检查（更严格）
        if category_code:
            # 必须是明确的品牌相关分类代码
            brand_categories = ['brand_info', 'brand_positioning', 'brand_vision_mission',
                             'brand_tone_values', 'brand_assets_identity']
            if any(cat in category_code for cat in brand_categories):
                # 还需要上下文支持
                if context and ('品牌' in context or 'brand' in context.lower()):
                    return True

        # 7. 默认拒绝（更严格，避免误识别）
        # 如果没有明确的证据，不创建品牌节点
        return False

    def _should_create_company_entity(self, name: str, classification: Dict[str, Any]) -> bool:
        if not name or len(name) < 2:
            return False
        if classification.get('is_blacklisted'):
            return False
        if classification.get('is_whitelisted'):
            return True
        confidence = classification.get('confidence', 0.0)
        if confidence < self.company_confidence_min:
            return False
        return True

    def _is_generic_name(self, name: str) -> bool:
        lowered = name.lower()
        for keyword in self.GENERIC_KEYWORDS:
            if keyword in name:
                return True
            if keyword.lower() in lowered:
                return True
        return False

    def _is_in_company_dictionary(self, name: str) -> bool:
        if not self.company_dict:
            return False
        normalized = self._normalize_name(name)
        return self.company_dict.exists(normalized)
    
    def _extract_potential_brand_from_title(self, document_title: str) -> Optional[str]:
        """
        从文档标题中提取潜在品牌名
        优化：提升品牌识别精准度
        
        规则：
        1. case_品牌名_... 格式
        2. proposal_品牌名_... 格式
        3. report_品牌名_... 格式
        """
        if not document_title:
            return None
        
        # 匹配格式：case_品牌名_... 或 proposal_品牌名_... 等
        patterns = [
            r'^(?:case|proposal|report|framework)_([^_]+?)_',  # case_品牌名_...
            r'^([^_]+?)_(?:案例|方案|报告|方法论)',  # 品牌名_案例
        ]
        
        for pattern in patterns:
            match = re.search(pattern, document_title)
            if match:
                potential_brand = match.group(1).strip()
                # 过滤掉明显不是品牌名的词
                if len(potential_brand) >= 2 and len(potential_brand) <= 20:
                    # 排除通用词
                    generic_words = {'45家', '品牌', '案例', '方案', '报告', '方法论', '策略', '指南'}
                    if potential_brand not in generic_words:
                        return potential_brand
        
        return None
    
    def _name_matches_potential_brand(self, entity_name: str, potential_brand: str) -> bool:
        """
        检查实体名是否匹配文档标题中提取的潜在品牌名
        支持部分匹配和规范化匹配
        """
        if not entity_name or not potential_brand:
            return False
        
        # 规范化：去除空格、转小写
        normalized_entity = self._normalize_name(entity_name)
        normalized_potential = self._normalize_name(potential_brand)
        
        # 完全匹配
        if normalized_entity == normalized_potential:
            return True
        
        # 包含匹配（实体名包含潜在品牌名，或反之）
        if normalized_potential in normalized_entity or normalized_entity in normalized_potential:
            # 确保不是部分词匹配（如"雅诗兰黛"不应匹配"雅诗"）
            if len(normalized_potential) >= 3:  # 至少3个字符才认为是有效匹配
                return True
        
        return False

    def _seems_generic_brand_name(self, name: str) -> bool:
        """
        检查是否为通用品牌名（增强版）
        优化：更准确地识别通用词，减少误判
        """
        # 检查后缀
        for suffix in self.GENERIC_SUFFIXES:
            if name.endswith(suffix):
                # 如果名称明显长于后缀，可能是品牌+后缀组合（如"苹果手机"）
                if len(name) > len(suffix) + 3:
                    continue
                return True
        
        # 检查英文模式（更完整的列表）
        if re.match(r'^[A-Za-z\s]+(Plan|Strategy|Guide|Report|Insight|Toolkit|System|Platform|Service|Solution|Framework|Methodology)$', name):
            return True
        
        # 检查过短的英文缩写（可能是通用缩写，但排除常见品牌缩写）
        if len(name) <= 3 and re.match(r'^[A-Za-z]+$', name):
            # 排除常见的品牌缩写（如 BMW, IBM, KFC, NBA, NFL, Nike, Adidas 等）
            common_brand_abbrevs = {'bmw', 'ibm', 'kfc', 'nba', 'nfl', 'nhl', 'mlb', 'nike', 'adidas', 
                                  'pwc', 'cpa', 'cfo', 'ceo', 'cto', 'cmo', 'cfo', 'ai', 'ui', 'ux'}
            if name.lower() not in common_brand_abbrevs:
                return True
        
        # 检查是否包含多个通用关键词
        generic_count = sum(1 for keyword in self.GENERIC_KEYWORDS if keyword in name)
        if generic_count >= 2:
            return True
        
        # 检查纯数字或符号
        if re.match(r'^[\d\s\-_\.]+$', name):
            return True
        
        # 检查句子片段模式（以常见动词/助词开头或结尾）
        sentence_starters = ['与', '和', '的', '了', '在', '是', '有', '为', '从', '到', '以', '对']
        sentence_enders = ['的', '了', '在', '是', '有', '为', '从', '到', '以', '对', '被', '把']
        if any(name.startswith(starter) for starter in sentence_starters):
            return True
        if any(name.endswith(ender) for ender in sentence_enders):
            return True
        
        return False

    @staticmethod
    def _normalize_name(name: Any) -> str:
        if not isinstance(name, str):
            return ""
        n = name.strip().strip('\'"“”‘’').strip()
        n = re.sub(r'\s{2,}', ' ', n)
        return n

