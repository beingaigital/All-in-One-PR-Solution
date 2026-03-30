#!/usr/bin/env python3
"""
实体关系提取器（v1.1 兼容层） Cursor Write It-qcf ;
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
import re

# --- 路径处理：支持直接 python path/to/file.py 执行 ---
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from core.knowledge.reference_loader import ReferenceSources
except Exception:  # pragma: no cover
    ReferenceSources = None

# 加载环境变量（确保 .env 文件被读取）
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env', override=True)
except ImportError:
    # 如果没有 dotenv，手动读取 .env 文件
    env_path = PROJECT_ROOT / '.env'
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

try:
    from core.processing.extractors.spo_extractor import SPOTripleExtractor
    from core.processing.extractors.org_classifier import OrganizationClassifier, EntityType
    from core.processing.company_dictionary import get_company_dictionary
    V1_1_MODULES_AVAILABLE = True
except ImportError as e:
    V1_1_MODULES_AVAILABLE = False
    print(f"⚠️ v1.1 模块导入失败: {e}")


class EntityRelationshipExtractor:
    """实体关系提取器（基于 v1.1 系统） Cursor Write It-qcf ;"""

    def __init__(self):
        """初始化实体关系提取器 Cursor Write It-qcf ;"""
        if not V1_1_MODULES_AVAILABLE:
            raise ImportError("v1.1 模块不可用，无法初始化实体提取器")

        # 禁用 OpenAI 和 HTTP 相关的详细日志，避免干扰进度条显示
        import logging
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)

        # 检测可用的 API key，决定使用 OpenRouter 还是 OpenAI
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()

        # 优先使用 OpenAI（如果存在），否则使用 OpenRouter
        use_openrouter = not openai_key and bool(openrouter_key)

        # 初始化 v1.1 组件
        self.spo_extractor = None
        try:
            if use_openrouter:
                # 使用 OpenRouter
                self.spo_extractor = SPOTripleExtractor(use_openrouter=True)
                # 静默初始化，不输出详细信息
            else:
                # 使用 OpenAI，需要指定 OpenAI 支持的模型名称
                # 默认使用 gpt-3.5-turbo（如果环境变量中有指定则使用环境变量的值）
                openai_model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
                self.spo_extractor = SPOTripleExtractor(
                    model_name=openai_model,
                    use_openrouter=False
                )
                # 静默初始化，不输出详细信息
        except Exception as e:
            # 如果初始化失败，警告但不阻止实体提取器工作
            # 实体提取器仍可以使用公司词典提取实体
            # 只在详细模式下输出警告
            if os.getenv("ENTITY_EXTRACTOR_VERBOSE", "0") == "1":
                print(f"⚠️ SPO提取器初始化失败: {e}")
                print("⚠️ 实体提取器将仅使用公司词典提取实体，不会从SPO三元组中提取实体")
            self.spo_extractor = None

        self.org_classifier = OrganizationClassifier()
        self.company_dict = get_company_dictionary()
        self.reference_sources = ReferenceSources() if ReferenceSources else None

    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """
        从文本中提取实体 Cursor Write It-qcf ;
        """
        entities = []
        seen_entities = set()

        # 1. 使用公司词典提取公司实体
        companies = self.company_dict.find_companies_in_text(text)
        for company in companies:
            if company not in seen_entities:
                entities.append({
                    'name': company,
                    'type': 'Company',
                    'confidence': 0.9,
                    'source': 'company_dictionary'
                })
                seen_entities.add(company)

        # 2. 使用 SPO 提取器提取实体（从三元组中提取 Subject 和 Object）
        # 如果 SPO 提取器不可用，跳过此步骤
        if self.spo_extractor:
            try:
                spo_result = self.spo_extractor.extract_triples_from_text(
                    text,
                    chunk_size=150,
                    overlap=30,
                    verbose=False
                )
                
                # 从三元组中提取实体
                triples = spo_result.get('triples', [])
                failed_chunks = spo_result.get('failed_chunks', [])
                
            # 如果有失败的块，静默处理，不输出警告（避免干扰进度条）
                
                for triple in triples:
                    subject = triple.get('subject', '').strip()
                    obj = triple.get('object', '').strip()

                    # 提取 Subject 实体（过滤无效值）
                    if subject and len(subject) > 1 and subject not in seen_entities:
                        # 排除占位符
                        if subject.lower() not in {'subject', 'predicate', 'object', 'n/a', 'na', 'null', 'none'}:
                            try:
                                entity_type, confidence = self._classify_entity(subject, text)
                                entities.append({
                                    'name': subject,
                                    'type': entity_type,
                                    'confidence': confidence,
                                    'source': 'spo_extractor'
                                })
                                seen_entities.add(subject)
                            except Exception as e:
                                # 分类失败不影响其他实体提取
                                pass

                    # 提取 Object 实体（过滤无效值）
                    if obj and len(obj) > 1 and obj not in seen_entities:
                        # 排除占位符
                        if obj.lower() not in {'subject', 'predicate', 'object', 'n/a', 'na', 'null', 'none'}:
                            try:
                                entity_type, confidence = self._classify_entity(obj, text)
                                entities.append({
                                    'name': obj,
                                    'type': entity_type,
                                    'confidence': confidence,
                                    'source': 'spo_extractor'
                                })
                                seen_entities.add(obj)
                            except Exception as e:
                                # 分类失败不影响其他实体提取
                                pass
            except Exception as e:
                # SPO提取失败不影响实体提取器工作
                # 只在非预期异常时输出详细错误（避免因LLM返回格式问题刷屏）
                import traceback
                error_msg = str(e)
                # 如果是常见的解析错误，简化输出
                if 'JSON' in error_msg or '解析' in error_msg or 'subject' in error_msg.lower():
                    # 静默处理常见错误，避免刷屏
                    pass
                # 静默处理错误，不输出详细信息（避免干扰进度条）
                # 只在详细模式下输出
                if os.getenv("ENTITY_EXTRACTOR_VERBOSE", "0") == "1":
                    print(f"⚠️ SPO 提取失败: {error_msg}")
                    traceback.print_exc()

        # 3. 使用正则表达式提取可能的实体（补充）
        # 注意：正则表达式提取容易产生误识别，应该更严格地过滤
        # 只在没有其他实体提取方法可用时才使用（SPO提取器失败时）
        # 如果SPO提取器可用，跳过正则表达式提取，避免产生过多噪音
        if not self.spo_extractor:
            # 提取2-6个中文字符的词语（可能是公司或品牌名）
            chinese_pattern = r'[\u4e00-\u9fa5]{2,6}'
            matches = re.findall(chinese_pattern, text)

            for match in matches:
                if match not in seen_entities and len(match) >= 2:
                    # 排除常见的停用词和通用词
                    stop_words = {
                        '哪些', '什么', '如何', '怎样', '为什么', '是否', '有没有',
                        '问题', '特点', '案例', '策略', '方法', '方式', '手段',
                        '进行', '开展', '实施', '执行', '完成', '实现',
                        '可以', '能够', '应该', '需要', '必须', '要求',
                        '这个', '那个', '这些', '那些', '其中', '其他',
                        '电商', '搜索', '转化', '效果', '阅读', '笔记', '数量',
                        '高速', '吹风', '上市', '第一', '代高', '相同', '变化',
                        '趋势', '北方', '空气', '拍立', '淘', '先进'
                    }
                    
                    # 排除包含常见业务关键词的词语
                    business_keywords = ['电商', '搜索', '转化', '效果', '阅读', '笔记', '数量',
                                       '高速', '吹风', '上市', '第一', '代高', '相同', '变化',
                                       '趋势', '北方', '空气', '拍立', '淘', '先进', '营销',
                                       '策略', '方案', '报告', '案例', '方法', '工具', '平台']

                    if match not in stop_words and not any(kw in match for kw in business_keywords):
                        try:
                            entity_type, confidence = self._classify_entity(match, text)
                            # 提高置信度阈值，只保留高置信度的实体
                            # 对于正则表达式提取的实体，要求更高的置信度（0.7+）
                            if confidence >= 0.7 and entity_type in ('company', 'brand'):
                                entities.append({
                                    'name': match,
                                    'type': entity_type,
                                    'confidence': confidence,
                                    'source': 'regex_extraction'
                                })
                                seen_entities.add(match)
                        except Exception:
                            # 分类失败不影响其他实体提取
                            pass

        # 4. 参考案例库进行规范化与别名映射
        if self.reference_sources:
            normalized = []
            for ent in entities:
                canonical, source = self.reference_sources.canonicalize(ent['name'])
                ent['canonical_name'] = canonical
                if source:
                    ent['provenance'] = source
                normalized.append(ent)
            entities = normalized

        return entities

    def extract_relationships(self, text: str) -> List[Dict[str, Any]]:
        """
        从文本中提取关系 Cursor Write It-qcf ;
        """
        relationships = []

        # 如果 SPO 提取器不可用，返回空列表
        if not self.spo_extractor:
            return relationships

        try:
            # 使用 SPO 提取器提取三元组
            spo_result = self.spo_extractor.extract_triples_from_text(
                text,
                chunk_size=150,
                overlap=30,
                verbose=False
            )

            # 转换 SPO 三元组为关系格式（过滤无效值）
            for triple in spo_result.get('triples', []):
                subject = triple.get('subject', '').strip()
                predicate = triple.get('predicate', '').strip()
                obj = triple.get('object', '').strip()
                
                # 验证三元组有效性
                if not all([subject, predicate, obj]):
                    continue
                
                # 排除占位符
                invalid_values = {'subject', 'predicate', 'object', 'n/a', 'na', 'null', 'none'}
                if (subject.lower() in invalid_values or 
                    predicate.lower() in invalid_values or 
                    obj.lower() in invalid_values):
                    continue
                
                if self.reference_sources:
                    subject, subj_source = self.reference_sources.canonicalize(subject)
                    obj, obj_source = self.reference_sources.canonicalize(obj)
                else:
                    subj_source = obj_source = None

                rel_entry = {
                    'subject': subject,
                    'predicate': predicate,
                    'object': obj,
                    'confidence': 0.8,  # SPO 提取的置信度
                    'source': 'spo_extractor'
                }
                if subj_source:
                    rel_entry['subject_provenance'] = subj_source
                if obj_source:
                    rel_entry['object_provenance'] = obj_source
                relationships.append(rel_entry)
        except Exception as e:
            # 简化错误输出，避免刷屏
            error_msg = str(e)
            if 'JSON' not in error_msg and '解析' not in error_msg:
                print(f"⚠️ SPO 关系提取失败: {error_msg}")

        return relationships

    def _classify_entity(self, name: str, context: str = "") -> tuple:
        """
        分类实体类型 Cursor Write It-qcf ;
        """
        if not name or not name.strip():
            return ('Unknown', 0.0)

        # 使用组织分类器
        try:
            classification = self.org_classifier.classify_entity(name, context=context)
            entity_type = classification.get('type', 'unknown')
            confidence = classification.get('confidence', 0.0)

            # 映射到标准类型
            type_mapping = {
                'brand': 'Brand',
                'company': 'Company',
                'company_type': 'CompanyType',
                'unknown': 'Unknown'
            }

            mapped_type = type_mapping.get(entity_type, 'Unknown')
            return (mapped_type, confidence)
        except Exception as e:
            # 如果分类失败，使用简单规则
            if self.company_dict.is_company(name):
                return ('Company', 0.7)
            else:
                return ('Unknown', 0.3)

    def extract_entities_from_text(self, text: str) -> List[Dict[str, Any]]:
        """
        从文本中提取实体（兼容方法） Cursor Write It-qcf ;
        """
        return self.extract_entities(text)

    def extract_relationships_from_text(self, text: str, entities: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """
        从文本中提取关系（兼容方法） Cursor Write It-qcf ;
        """
        relationships = self.extract_relationships(text)

        # 如果调用方提供了实体，尝试填充缺失字段保持兼容
        if entities:
            entity_names = {e.get("name") for e in entities if isinstance(e, dict)}
            for rel in relationships:
                if not rel.get("subject") and entity_names:
                    rel["subject"] = next(iter(entity_names))
                if not rel.get("object") and entity_names:
                    rel["object"] = next(iter(entity_names))
        return relationships


def test_entity_extractor():
    """测试实体提取器 Cursor Write It-qcf ;"""
    test_text = """
    小米公司是一家专注于智能硬件和电子产品研发的移动互联网公司。
    小米品牌在智能手机市场占有重要地位，与华为、OPPO等品牌竞争。
    小米汽车是小米集团的新业务，专注于电动汽车领域。
    """

    print("🧪 测试实体关系提取器（v1.1）")
    print("=" * 60)

    try:
        extractor = EntityRelationshipExtractor()

        # 提取实体
        entities = extractor.extract_entities(test_text)
        print(f"\n📊 提取到 {len(entities)} 个实体:")
        for entity in entities[:10]:  # 只显示前10个
            print(f"  - {entity['name']} ({entity['type']}, 置信度: {entity['confidence']:.2f})")

        # 提取关系
        relationships = extractor.extract_relationships(test_text)
        print(f"\n🔗 提取到 {len(relationships)} 个关系:")
        for rel in relationships[:5]:  # 只显示前5个
            print(f"  - {rel['subject']} --[{rel['predicate']}]--> {rel['object']}")

        return entities, relationships

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return [], []


if __name__ == "__main__":
    test_entity_extractor()
