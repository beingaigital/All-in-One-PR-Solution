#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强的知识图谱写入器
实现CategoryL1/CategoryL2/Section/Company节点结构 + SPO三元组集成
"""

import json
import logging
import os
import sys
import uuid
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 可选依赖：进度条和重试机制
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    tqdm = None

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False
    retry = lambda *args, **kwargs: lambda f: f  # 无操作装饰器

module_logger = logging.getLogger("KGWriterSetup")

try:
    from neo4j import GraphDatabase
except ImportError:
    module_logger.error("❌ 需要安装neo4j: pip install neo4j")
    sys.exit(1)

try:
    from core.processing.extractors.spo_extractor import SPOTripleExtractor
    SPO_AVAILABLE = True
except ImportError:
    SPO_AVAILABLE = False
    module_logger.warning("⚠️ SPO提取器不可用")

try:
    from core.processing.extractors.entity_extractor import EntityRelationshipExtractor
    ENTITY_EXTRACTOR_AVAILABLE = True
except ImportError:
    ENTITY_EXTRACTOR_AVAILABLE = False
    module_logger.warning("⚠️ 实体提取器不可用")

try:
    from core.processing.extractors.org_classifier import OrganizationClassifier
    ORG_CLASSIFIER_AVAILABLE = True
except ImportError:
    ORG_CLASSIFIER_AVAILABLE = False
    module_logger.warning("⚠️ 组织分类器不可用")

from core.common.pr_category_schema import (
    CATEGORY_SCHEMA,
    get_category_l2_list,
    classify_section,
    get_category_by_code
)
from .json_loader import extract_sections_from_json
from .entity_linker import EntityLinker

# 可选：公司/品牌词典用于保守放行（优先信任）
try:
    from core.processing.company_dictionary import CompanyDictionary
    COMPANY_DICT_AVAILABLE = True
except Exception:
    COMPANY_DICT_AVAILABLE = False
    CompanyDictionary = None


class EnhancedKGWriter:
    """增强的知识图谱写入器"""
    
    def __init__(
        self,
        uri: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        use_spo: bool = True,
        use_entity_extractor: bool = True
    ):
        """
        初始化增强KG写入器
        
        Args:
            uri: Neo4j URI
            username: 用户名
            password: 密码
            database: 数据库名
            use_spo: 是否使用SPO提取器
            use_entity_extractor: 是否使用实体提取器
        """
        self._setup_logging()
        # 加载环境变量
        try:
            from dotenv import load_dotenv
            load_dotenv('.env', override=True)
        except:
            # 手动读取.env文件
            if os.path.exists('.env'):
                with open('.env', 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            os.environ[key.strip()] = value.strip()
        
        self.uri = uri or os.getenv('NEO4J_URI', 'neo4j://127.0.0.1:7687')
        self.username = username or os.getenv('NEO4J_USERNAME', 'neo4j')
        self.password = password or os.getenv('NEO4J_PASSWORD', '')
        self.database = database or os.getenv('NEO4J_DATABASE', 'neo4j')
        self.checkpoint_path = Path(os.getenv('KG_WRITER_CHECKPOINT', 'data/.kg_writer_checkpoint.json'))
        self.completed_files: Dict[str, Dict[str, Any]] = {}
        
        # 静默连接，不输出详细信息（避免干扰进度条）
        
        # 连接Neo4j
        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.username, self.password),
            max_connection_lifetime=30 * 60,
            max_connection_pool_size=50,
            connection_acquisition_timeout=2 * 60,
            keep_alive=True,
        )
        
        # 测试连接
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run("RETURN 1 as test")
                result.single()
            # 静默连接成功，不输出详细信息
        except Exception as e:
            self.logger.error("❌ Neo4j连接失败", exc_info=True)
            raise
        
        # 初始化提取器
        self.use_spo = use_spo and SPO_AVAILABLE
        self.use_entity_extractor = use_entity_extractor and ENTITY_EXTRACTOR_AVAILABLE
        
        # 静默初始化，不输出详细信息
        
        # 初始化组织分类器
        if ORG_CLASSIFIER_AVAILABLE:
            try:
                self.org_classifier = OrganizationClassifier()
                # 静默初始化，不输出详细信息
            except Exception as e:
                # 只在失败时输出警告
                self.logger.warning(f"⚠️ 组织分类器初始化失败: {e}")
                self.org_classifier = None
        else:
            self.org_classifier = None
        
        if self.use_spo:
            try:
                self.spo_extractor = SPOTripleExtractor(
                    temperature=0.0,
                    use_openrouter=True
                )
                # 静默初始化，不输出详细信息
            except Exception as e:
                # 只在失败时输出警告
                self.logger.warning(f"⚠️ SPO提取器初始化失败: {e}")
                self.use_spo = False
        
        if self.use_entity_extractor:
            try:
                self.entity_extractor = EntityRelationshipExtractor()
                # 静默初始化，不输出详细信息
            except Exception as e:
                # 只在失败时输出警告
                self.logger.warning(f"⚠️ 实体提取器初始化失败: {e}")
                self.logger.warning("⚠️ 这将导致无法创建Company和Brand节点，请检查API key配置")
                self.use_entity_extractor = False
        
        # 统计信息
        self.stats = {
            'category_l1_created': 0,
            'category_l2_created': 0,
            'sections_created': 0,
            'companies_created': 0,
            'brands_created': 0,
            'brands_skipped': 0,
            'company_types_created': 0,
            'spo_relations_created': 0,
            'involved_in_category_relations': 0,
            'belongs_to_brand_relations': 0,
            'belongs_to_type_relations': 0
        }

        # 初始化分类器与公司/品牌词典
        self.org_classifier = OrganizationClassifier() if ORG_CLASSIFIER_AVAILABLE else None
        # 仅用于校验，不落盘：save_to_file=False 可避免运行时自动写 company_dictionary.json
        self.company_dict = CompanyDictionary(save_to_file=True) if COMPANY_DICT_AVAILABLE and CompanyDictionary else None
        self.entity_linker = EntityLinker(
            driver=self.driver,
            database=self.database,
            stats=self.stats,
            org_classifier=self.org_classifier,
            company_dict=self.company_dict,
        )

    def _setup_logging(self):
        """配置日志系统"""
        # 禁用 OpenAI 和 HTTP 相关的详细日志，避免干扰进度条显示
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        # 降低 Neo4j 驱动日志级别，隐藏已存在约束/索引的提示
        logging.getLogger("neo4j").setLevel(logging.WARNING)
        logging.getLogger("neo4j").propagate = False
        
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s",
            handlers=[logging.StreamHandler()],
        )
        self.logger = logging.getLogger("KGWriter")

    def create_schema(self):
        """创建Neo4j Schema和分类节点"""
        self.logger.info("🏗️ 创建增强图谱Schema...")
        self.logger.info("-" * 70)
        
        schema_queries = [
            # CategoryL1节点约束
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:CategoryL1) REQUIRE c.code IS UNIQUE",
            # CategoryL2节点约束
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:CategoryL2) REQUIRE c.code IS UNIQUE",
            # Section节点约束
            "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Section) REQUIRE s.id IS UNIQUE",
            # Company节点约束
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Company) REQUIRE c.name IS UNIQUE",
            # Brand节点约束
            "CREATE CONSTRAINT IF NOT EXISTS FOR (b:Brand) REQUIRE b.name IS UNIQUE",
            # CompanyType节点约束
            "CREATE CONSTRAINT IF NOT EXISTS FOR (ct:CompanyType) REQUIRE ct.code IS UNIQUE",
            # Campaign节点约束（用于SPO中的活动）
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Campaign) REQUIRE c.name IS UNIQUE",
            # Concept节点约束（用于SPO中的概念）
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE",
            
            # 索引
            "CREATE INDEX IF NOT EXISTS FOR (c:Company) ON (c.name)",
        ]
        
        with self.driver.session(database=self.database) as session:
            for query in schema_queries:
                try:
                    session.run(query)
                except Exception:
                    self.logger.warning("  ⚠️ Schema创建警告", exc_info=True)
        
        self.logger.info("✅ Schema创建完成")
        
        # 创建CategoryL1和CategoryL2节点
        self._create_category_nodes()
        
        # 创建CompanyType节点
        self._create_company_type_nodes()
    
    def _create_category_nodes(self):
        """创建所有CategoryL1和CategoryL2节点"""
        self.logger.info("📋 创建分类节点...")
        
        # 检查是否已存在
        with self.driver.session(database=self.database) as session:
            result = session.run("MATCH (c:CategoryL1) RETURN count(c) as count")
            existing_l1 = result.single()['count']
            result = session.run("MATCH (c:CategoryL2) RETURN count(c) as count")
            existing_l2 = result.single()['count']
            
            if existing_l1 == len(CATEGORY_SCHEMA) and existing_l2 >= len(CATEGORY_SCHEMA) * 5:
                self.logger.info(f"  ⚠️ 分类节点已存在（L1: {existing_l1}, L2: {existing_l2}），跳过创建")
                self.stats['category_l1_created'] = existing_l1
                self.stats['category_l2_created'] = existing_l2
                return
        
        with self.driver.session(database=self.database) as session:
            # 创建CategoryL1节点
            for l1_code, l1_data in CATEGORY_SCHEMA.items():
                try:
                    session.run("""
                        MERGE (c1:CategoryL1 {code: $code})
                        ON CREATE SET 
                            c1.label = $label,
                            c1.created_at = datetime()
                        ON MATCH SET
                            c1.label = $label
                    """, code=l1_code, label=l1_data['label'])
                    self.stats['category_l1_created'] += 1
                except Exception:
                    self.logger.warning(f"  ⚠️ 创建CategoryL1失败 {l1_code}", exc_info=True)
            
            # 创建CategoryL2节点并连接到CategoryL1
            for l1_code, l1_data in CATEGORY_SCHEMA.items():
                for l2_subcode, l2_data in l1_data['sub_categories'].items():
                    l2_code = f"{l1_code}.{l2_subcode}"
                    
                    try:
                        # 创建CategoryL2节点
                        session.run("""
                            MERGE (c2:CategoryL2 {code: $code})
                            ON CREATE SET 
                                c2.label = $label,
                                c2.parent_code = $parent_code,
                                c2.keywords = $keywords,
                                c2.created_at = datetime()
                            ON MATCH SET
                                c2.label = $label,
                                c2.keywords = $keywords
                        """, 
                            code=l2_code,
                            label=l2_data['label'],
                            parent_code=l1_code,
                            keywords=l2_data['keywords']
                        )
                        
                        # 连接到CategoryL1
                        session.run("""
                            MATCH (c1:CategoryL1 {code: $parent_code})
                            MATCH (c2:CategoryL2 {code: $code})
                            MERGE (c1)-[:HAS_SUBCATEGORY]->(c2)
                        """, parent_code=l1_code, code=l2_code)
                        
                        self.stats['category_l2_created'] += 1
                    except Exception:
                        self.logger.warning(f"  ⚠️ 创建CategoryL2失败 {l2_code}", exc_info=True)
        
        self.logger.info(f"✅ 创建了 {self.stats['category_l1_created']} 个CategoryL1节点")
        self.logger.info(f"✅ 创建了 {self.stats['category_l2_created']} 个CategoryL2节点")
    
    def _create_company_type_nodes(self):
        """创建所有CompanyType节点"""
        if not self.org_classifier:
            self.logger.warning("⚠️ 组织分类器不可用，跳过CompanyType节点创建")
            return
        
        self.logger.info("📋 创建CompanyType节点...")
        
        company_types = self.org_classifier.get_company_type_nodes()
        
        with self.driver.session(database=self.database) as session:
            for ct in company_types:
                try:
                    session.run("""
                        MERGE (ct:CompanyType {code: $code})
                        ON CREATE SET
                            ct.label = $label,
                            ct.created_at = datetime()
                        ON MATCH SET
                            ct.label = $label
                    """, code=ct['code'], label=ct['label'])
                    self.stats['company_types_created'] += 1
                except Exception:
                    self.logger.warning(f"  ⚠️ 创建CompanyType失败 {ct['code']}", exc_info=True)
        
        self.logger.info(f"✅ 创建了 {self.stats['company_types_created']} 个CompanyType节点")

    def process_json_files(
        self, 
        json_dir: str = "data/json_structured", 
        resume: bool = True, 
        reset_checkpoint: bool = False,
        parallel: bool = False,
        max_workers: int = 4
    ):
        """
        处理JSON文件并写入Neo4j
        
        Args:
            json_dir: JSON文件目录
            resume: 是否启用断点续跑
            reset_checkpoint: 是否重置检查点
            parallel: 是否并行处理（实验性功能）
            max_workers: 并行处理时的最大工作线程数
        """
        self.logger.info("📊 开始处理JSON文件...")
        self.logger.info("=" * 70)
        
        json_path = Path(json_dir)
        if not json_path.exists():
            self.logger.error(f"❌ JSON目录不存在: {json_dir}")
            return
        
        json_files = list(json_path.glob("*.json"))
        if not json_files:
            self.logger.error("❌ 未找到JSON文件")
            return
        
        self.logger.info(f"📁 找到 {len(json_files)} 个JSON文件")

        if reset_checkpoint and self.checkpoint_path.exists():
            try:
                self.checkpoint_path.unlink()
                self.logger.info("ℹ️ 已清空断点记录")
            except Exception as exc:
                self.logger.warning(f"⚠️ 无法清空断点记录: {exc}")

        if resume:
            self.completed_files = self._load_checkpoint()
            if self.completed_files:
                self.logger.info(f"ℹ️ 断点续跑启用，已完成 {len(self.completed_files)} 个文件")
        else:
            self.completed_files = {}
        
        # 过滤已完成的文件
        pending_files = [
            f for f in json_files 
            if not (resume and f.name in self.completed_files)
        ]
        
        if not pending_files:
            self.logger.info("✅ 所有文件已完成处理")
            self._show_statistics()
            return
        
        # 使用进度条（如果可用）
        if TQDM_AVAILABLE and not parallel:
            file_iterator = tqdm(
                pending_files, 
                desc="📄 处理文件", 
                unit="文件",
                disable=False,
                ncols=100,  # 限制进度条宽度
                bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]'  # 简化格式
            )
        else:
            file_iterator = pending_files
        
        # 并行或串行处理
        if parallel:
            self._process_files_parallel(pending_files, max_workers, resume)
        else:
            self._process_files_sequential(file_iterator, resume)
        
        # 创建Company与CategoryL2的汇总关系
        self.logger.info("📊 创建Company-CategoryL2汇总关系...")
        self._create_company_category_summary()
        
        # 显示统计
        self._show_statistics()
    
    def _process_files_sequential(self, file_iterator, resume: bool):
        """串行处理文件（带进度显示）"""
        for json_file in file_iterator:
            if isinstance(json_file, Path):
                file_name = json_file.name
            else:
                # tqdm 包装的对象
                json_file = file_iterator.n if hasattr(file_iterator, 'n') else json_file
                file_name = str(json_file)
                json_file = Path(json_file) if isinstance(json_file, str) else json_file
            
            if TQDM_AVAILABLE and hasattr(file_iterator, 'set_postfix'):
                file_iterator.set_postfix({'当前': file_name[:30]})
            
            # 不输出文件处理开始信息，让进度条更清晰
            # self.logger.info(f"📄 处理: {file_name}")
            try:
                start_time = time.time()
                sections_done = self._process_single_json(json_file)
                elapsed = time.time() - start_time
                
                if resume:
                    self._mark_file_completed(file_name, sections_done)
                
                if TQDM_AVAILABLE and hasattr(file_iterator, 'set_postfix'):
                    file_iterator.set_postfix({
                        '文件': file_name[:20],
                        'sections': sections_done,
                        '耗时': f"{elapsed:.1f}s"
                    })
            except Exception as e:
                self.logger.error(f"  ❌ 处理失败: {e}", exc_info=True)
    
    def _process_files_parallel(self, json_files: List[Path], max_workers: int, resume: bool):
        """并行处理文件（实验性功能）"""
        self.logger.info(f"🚀 启用并行处理模式（{max_workers} 个工作线程）")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._process_single_json_safe, f, resume): f 
                for f in json_files
            }
            
            completed = 0
            total = len(futures)
            
            for future in as_completed(futures):
                json_file = futures[future]
                completed += 1
                try:
                    sections_done = future.result()
                    self.logger.info(
                        f"✅ [{completed}/{total}] {json_file.name}: {sections_done} sections"
                    )
                except Exception as e:
                    self.logger.error(f"❌ [{completed}/{total}] {json_file.name}: {e}", exc_info=True)
    
    def _process_single_json_safe(self, json_file: Path, resume: bool) -> int:
        """安全处理单个JSON文件（用于并行处理）"""
        try:
            sections_done = self._process_single_json(json_file)
            if resume:
                self._mark_file_completed(json_file.name, sections_done)
            return sections_done
        except Exception as e:
            self.logger.error(f"处理 {json_file.name} 时出错: {e}", exc_info=True)
            raise
    
    def _process_single_json(self, json_file: Path):
        """处理单个JSON文件（带重试和检查点）"""
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 提取文档标题（仅用于 section 标题回填，不参与品牌/公司提取）
        doc_title = data.get('document_title', json_file.stem)
        
        # 解析Section列表
        sections = extract_sections_from_json(data, json_file.stem, doc_title)
        
        # 不输出详细信息，避免干扰进度条
        if not sections:
            self.logger.warning("  ⚠️ 未从JSON中解析到Section")
            return 0

        # 批量写入基础 Section 数据（静默执行）
        self._batch_write_sections(sections)
        
        # 处理每个Section（带重试和中间检查点）
        success_count = 0
        total = len(sections)
        
        # 计算检查点间隔（每10%保存一次）
        checkpoint_interval = max(1, total // 10) if total > 10 else max(1, total // 5)
        
        # 仅使用文件级进度条，禁用节级进度条以保持输出简洁
        section_iterator = enumerate(sections)
        
        for i, section in section_iterator:
            if not isinstance(section, dict):
                self.logger.warning(
                    f"  ⚠️ Section结构异常 index={i}, 类型={type(section).__name__}, 内容={str(section)[:80]}"
                )
                continue
            
            try:
                # 提取实体并连接（带重试）
                if self.use_entity_extractor:
                    # 优化：将文档标题和section标题也加入实体提取的文本中，提升品牌识别精准度
                    section_text = section.get('text', '') or section.get('clean_text', '')
                    section_title = section.get('title', '')
                    section_id_text = str(section.get('id', '') or '')
                    
                    # 仅使用 json_structured 中的 id/title/text 作为实体提取上下文
                    enhanced_text_parts = [
                        part for part in (section_id_text, section_title, section_text) if part
                    ]
                    enhanced_text = "\n".join(enhanced_text_parts)
                    
                    entities = self._extract_entities_with_retry(enhanced_text)
                    # 静默处理，不输出调试信息，避免干扰进度条
                    self.entity_linker.link(section['id'], entities, section)
                
                # 提取SPO三元组（可选，如果失败不影响主流程）
                if self.use_spo:
                    try:
                        spo_triples = self._extract_spo_with_retry(section)
                        self._create_spo_relations(spo_triples, section['id'], section)
                    except Exception as e:
                        # SPO提取失败不影响主流程
                        pass
                
                success_count += 1
                
                # 定期保存中间检查点
                if (i + 1) % checkpoint_interval == 0:
                    self._save_section_checkpoint(json_file.name, i + 1, total)
                    
            except Exception as e:
                # 静默处理错误，避免干扰进度条
                # 只在详细模式下输出错误信息
                if os.getenv("KG_WRITER_VERBOSE", "0") == "1":
                    section_id = section.get('id') if isinstance(section, dict) else f"index_{i}"
                    self.logger.warning(f"  ⚠️ Section处理失败 {section_id}: {e}", exc_info=True)
                continue
        
        # 只在完成时输出简要统计，不输出每个section的详细信息
        if success_count < len(sections):
            self.logger.warning(f"  ⚠️ 完成: {success_count}/{len(sections)} sections (部分失败)")
        # 成功时不输出，避免干扰进度条
        
        return success_count
    
    def _extract_entities_with_retry(self, text: str):
        """带重试的实体提取"""
        if not self.use_entity_extractor:
            return []
        
        if TENACITY_AVAILABLE:
            @retry(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                reraise=True
            )
            def _extract():
                return self.entity_extractor.extract_entities_from_text(text)
            return _extract()
        else:
            # 无重试机制，直接调用
            return self.entity_extractor.extract_entities_from_text(text)
    
    def _extract_spo_with_retry(self, section: Dict[str, Any]):
        """带重试的SPO提取（失败不影响主流程）"""
        if not self.use_spo:
            return []
        
        if TENACITY_AVAILABLE:
            @retry(
                stop=stop_after_attempt(2),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                reraise=False
            )
            def _extract():
                return self._extract_spo_for_section(section)
            try:
                return _extract()
            except Exception:
                return []  # SPO提取失败返回空列表
        else:
            # 无重试机制，直接调用
            try:
                return self._extract_spo_for_section(section)
            except Exception:
                return []
    
    def _save_section_checkpoint(self, file_name: str, processed: int, total: int):
        """保存Section级别的中间检查点"""
        try:
            if file_name not in self.completed_files:
                self.completed_files[file_name] = {}
            self.completed_files[file_name]['sections_processed'] = processed
            self.completed_files[file_name]['sections_total'] = total
            self.completed_files[file_name]['updated_at'] = datetime.utcnow().isoformat() + 'Z'
            # 不每次都保存到文件，减少IO开销（在主流程中统一保存）
        except Exception as e:
            self.logger.debug(f"保存中间检查点失败: {e}")
    
    def _create_document_brand_node(
        self, 
        brand_name: str, 
        sections: List[Dict[str, Any]], 
        doc_title: str,
        file_stem: str
    ):
        """
        创建文档级别的品牌节点并关联到所有Section
        
        优化：如果JSON文件中已有brand字段，直接使用，避免重复提取
        优化：提取核心品牌名，避免使用过长的描述性文本
        
        Args:
            brand_name: 品牌名称（从文档级别brand字段提取）
            sections: Section列表
            doc_title: 文档标题
            file_stem: 文件名（不含扩展名）
        """
        if not brand_name or len(brand_name) < 2:
            return
        
        # 优化：如果品牌名过长（>10个字符），尝试提取核心品牌名
        normalized_brand_name = self._extract_core_brand_name(brand_name)
        
        with self.driver.session(database=self.database) as session:
            # 创建品牌节点（高置信度，已验证）
            session.run("""
                MERGE (b:Brand {name: $name})
                ON CREATE SET 
                    b.type = 'brand',
                    b.level = 'group',
                    b.created_at = datetime(),
                    b.uncertain = false,
                    b.confidence = 0.9,
                    b.source = $source,
                    b.verified = true,
                    b.source_priority = 'document_level'
                ON MATCH SET
                    b.verified = COALESCE(b.verified, true),
                    b.confidence = CASE 
                        WHEN b.confidence < 0.9 THEN 0.9 
                        ELSE b.confidence 
                    END,
                    b.source_priority = COALESCE(b.source_priority, 'document_level')
            """,
                name=normalized_brand_name,
                source=doc_title or file_stem
            )
            self.stats['brands_created'] += 1
            
            # 关联品牌到所有Section
            section_ids = [s.get('id') for s in sections if s.get('id')]
            if section_ids:
                session.run("""
                    MATCH (b:Brand {name: $brand_name})
                    UNWIND $section_ids as section_id
                    MATCH (s:Section {id: section_id})
                    MERGE (s)-[:MENTIONS_BRAND]->(b)
                """,
                    brand_name=normalized_brand_name,
                    section_ids=section_ids
                )
                self.stats['belongs_to_brand_relations'] += len(section_ids)
            
            # 静默创建，不输出详细信息
    
    def _extract_core_brand_name(self, brand_name: str) -> str:
        """
        从品牌名中提取核心品牌名，避免使用过长的描述性文本
        
        例如：
        - "奥迪新零售电商业务竞标方案" -> "奥迪"
        - "一汽丰田2021年度数字营销电商策略" -> "一汽丰田"
        - "广汽本田新能源新零售模式" -> "广汽本田"
        
        Args:
            brand_name: 原始品牌名
        
        Returns:
            提取的核心品牌名
        """
        if not brand_name or len(brand_name) <= 6:
            return brand_name
        
        import re
        
        # 常见业务关键词（用于识别品牌名边界）
        business_keywords = [
            '新零售', '电商', '数字营销', '体验', '竞标', '方案', '策略', '业务', 
            '模式', '年度', '2021', '2022', '2023', '2024', '2025',
            '新能源', '新零售模式', '电商业务', '竞标方案'
        ]
        
        # 尝试提取到第一个业务关键词之前
        for keyword in business_keywords:
            if keyword in brand_name:
                idx = brand_name.find(keyword)
                if idx > 0 and idx <= 10:  # 品牌名通常不超过10个字符
                    candidate = brand_name[:idx]
                    # 确保提取的部分是有效的品牌名（至少2个字符，不全是数字）
                    if len(candidate) >= 2 and not re.match(r'^\d+$', candidate):
                        return candidate
        
        # 如果没有找到业务关键词，尝试提取前2-6个字符
        # 常见品牌名长度：2-4个字符（如"奥迪"、"小米"、"华为"）
        for length in [6, 5, 4, 3, 2]:
            if len(brand_name) >= length:
                candidate = brand_name[:length]
                # 排除纯数字和明显不是品牌名的词
                if not re.match(r'^\d+$', candidate) and candidate not in ['新零售', '电商', '数字营销']:
                    return candidate
        
        # 如果都不行，返回原始品牌名
        return brand_name

    def _batch_write_sections(self, sections: List[Dict[str, Any]], batch_size: int = 500):
        """批量写入 Section 节点和分类关系（带事务管理）"""
        if not sections:
            return

        query = """
        UNWIND $batch as row
        MERGE (s:Section {id: row.id})
        ON CREATE SET
            s.clean_text = row.clean_text,
            s.category_code = row.level2
        ON MATCH SET
            s.clean_text = row.clean_text,
            s.category_code = row.level2
        WITH s, row
        WHERE row.level2 IS NOT NULL AND row.level2 <> ''
        MATCH (c2:CategoryL2 {code: row.level2})
        MERGE (c2)-[:HAS_SECTION]->(s)
        """

        total = len(sections)
        with self.driver.session(database=self.database) as session:
            # 使用事务批量写入，提高效率和一致性
            with session.begin_transaction() as tx:
                try:
                    for i in range(0, total, batch_size):
                        batch = sections[i:i + batch_size]
                        payload = []
                        for item in batch:
                            clean_text = (item.get('clean_text') or item.get('text') or '')[:10000]
                            payload.append({
                                'id': item.get('id'),
                                'clean_text': clean_text,
                                'level2': item.get('level2', '')
                            })

                        tx.run(query, batch=payload)
                        self.stats['sections_created'] += len(payload)
                    
                    tx.commit()
                except Exception as exc:
                    tx.rollback()
                    start = i if 'i' in locals() else 0
                    end = i + len(batch) if 'batch' in locals() else 0
                    self.logger.error(
                        f"  ❌ 批量写入失败 (索引 {start}-{end})，已回滚",
                        exc_info=True
                    )
                    raise exc

    def _load_checkpoint(self) -> Dict[str, Dict[str, Any]]:
        if not self.checkpoint_path.exists():
            return {}
        try:
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data.get('completed_files', {})
        except Exception as exc:
            self.logger.warning(f"⚠️ 断点记录读取失败: {exc}")
        return {}

    def _save_checkpoint(self):
        try:
            self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.checkpoint_path, 'w', encoding='utf-8') as f:
                json.dump({'completed_files': self.completed_files}, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            self.logger.warning(f"⚠️ 断点记录保存失败: {exc}")

    def _mark_file_completed(self, file_name: str, sections_done: int):
        """标记文件完成并保存检查点"""
        self.completed_files[file_name] = {
            'sections': sections_done,
            'sections_processed': sections_done,  # 兼容中间检查点
            'updated_at': datetime.utcnow().isoformat() + 'Z'
        }
        self._save_checkpoint()
    
    def _extract_sections_from_json(self, data: Dict, doc_name: str, doc_title: str) -> List[Dict]:
        """
        从JSON中提取Section列表：根据结构特征分发给不同解析器
        """
        is_hierarchical = False
        for key, value in data.items():
            if key in ['document_title', 'metadata']:
                continue
            if isinstance(value, dict):
                if 'chapters' in value:
                    is_hierarchical = True
                    break
                for sub_value in value.values():
                    if isinstance(sub_value, dict) and 'chapters' in sub_value:
                        is_hierarchical = True
                        break
            if is_hierarchical:
                break

        if is_hierarchical:
            return self._parse_hierarchical_json(data, doc_name, doc_title)
        return self._parse_flat_json(data, doc_name, doc_title)

    def _parse_hierarchical_json(self, data: Dict, doc_name: str, doc_title: str) -> List[Dict]:
        """处理嵌套/PDF解析器格式"""
        sections: List[Dict[str, Any]] = []
        for level1_key, level1_data in data.items():
            if level1_key in ['document_title', 'metadata', '其他章节']:
                continue
            if not isinstance(level1_data, dict):
                continue

            level1_label = level1_data.get('label', level1_key)
            level1_code = level1_key

            for level2_key, level2_data in level1_data.items():
                if level2_key == 'label':
                    continue
                if not (isinstance(level2_data, dict) and 'chapters' in level2_data):
                    continue

                level2_label = level2_data.get('label', level2_key)
                level2_code = f"{level1_code}.{level2_key}"
                chapters = level2_data.get('chapters', {})

                for chapter_title, chapter_content in chapters.items():
                    text = str(chapter_content or '').strip()
                    if len(text) < 10:
                        continue

                    section_id = f"{doc_name}_{level1_code}_{level2_key}_{len(sections)}"
                    sections.append({
                        'id': section_id,
                        'title': chapter_title,
                        'text': text,
                        'level1': level1_code,
                        'level1_label': level1_label,
                        'level2': level2_code,
                        'level2_label': level2_label,
                        'source': doc_name,
                        'document_title': doc_title
                    })
        return sections

    def _parse_flat_json(self, data: Dict, doc_name: str, doc_title: str) -> List[Dict]:
        """处理扁平结构（当前chunks格式）"""
        sections: List[Dict[str, Any]] = []
        for key, value in data.items():
            if key in ['document_title', 'metadata']:
                continue

            normalized_value = value
            if isinstance(normalized_value, list):
                flattened_parts = []
                for item in normalized_value:
                    if isinstance(item, dict):
                        flattened_parts.append(
                            item.get('text') or item.get('content') or item.get('value') or ''
                        )
                    else:
                        flattened_parts.append(str(item))
                normalized_value = "\n".join(part for part in flattened_parts if part)
            elif isinstance(normalized_value, dict):
                normalized_value = (
                    normalized_value.get('text')
                    or normalized_value.get('content')
                    or normalized_value.get('value')
                    or ''
                )

            if not isinstance(normalized_value, str):
                normalized_value = str(normalized_value or '')

            normalized_value = normalized_value.strip()
            if not normalized_value:
                continue

            level1_code, level2_code, level2_label = classify_section(
                title=key,
                content=normalized_value[:200]
            )
            section_id = f"{doc_name}_{level1_code}_{level2_code.split('.')[-1]}_{len(sections)}"
            l2_meta = get_category_by_code(level2_code)

            sections.append({
                'id': section_id,
                'title': key,
                'text': normalized_value,
                'level1': level1_code,
                'level1_label': l2_meta['l1_label'] if l2_meta else level1_code,
                'level2': level2_code,
                'level2_label': level2_label,
                'source': doc_name,
                'document_title': doc_title
            })
        return sections
    
    def _create_section(self, section: Dict, doc_title: str):
        """创建Section节点并连接到CategoryL2"""
        section_id = section['id']
        level2_code = section.get('level2', '')
        
        text = (section.get('clean_text') or section.get('text') or '')[:10000]
        
        with self.driver.session(database=self.database) as session:
            # 创建Section节点
            session.run("""
                MERGE (s:Section {id: $id})
                ON CREATE SET 
                    s.clean_text = $clean_text,
                    s.category_code = $level2
                ON MATCH SET
                    s.clean_text = $clean_text,
                    s.category_code = $level2
            """,
                id=section_id,
                clean_text=text,
                level2=level2_code
            )
            
            # 连接到CategoryL2
            if level2_code:
                session.run("""
                    MATCH (s:Section {id: $section_id})
                    MATCH (c2:CategoryL2 {code: $level2_code})
                    MERGE (c2)-[:HAS_SECTION]->(s)
                """, section_id=section_id, level2_code=level2_code)
            
            self.stats['sections_created'] += 1
    
    
    
    
    def _extract_spo_for_section(self, section: Dict) -> List[Dict]:
        """为Section提取SPO三元组"""
        if not self.use_spo:
            return []
        
        text = section.get('text', '')
        if not text or len(text) < 20:
            return []
        
        try:
            result = self.spo_extractor.extract_triples_from_text(
                text,
                chunk_size=200,
                overlap=30,
                verbose=False
            )
            
            triples = result.get('triples', [])
            # 添加section信息
            for triple in triples:
                triple['section_id'] = section.get('id', '')
                triple['level1'] = section.get('level1', '')
                triple['level2'] = section.get('level2', '')
            
            return triples
        except Exception as e:
            return []
    
    def _create_spo_relations(self, triples: List[Dict], section_id: str, section: Dict):
        """创建SPO关系"""
        with self.driver.session(database=self.database) as session:
            for triple in triples:
                subject = triple.get('subject', '').strip()
                predicate = triple.get('predicate', '').strip()
                obj = triple.get('object', '').strip()
                
                if not all([subject, predicate, obj]):
                    continue
                
                level2_code = section.get('level2', '')
                
                # 尝试将subject映射到Company
                subject_company = session.run("""
                    MATCH (c:Company)
                    WHERE toLower(c.name) = toLower($subject)
                    RETURN c LIMIT 1
                """, subject=subject).single()
                
                if not subject_company:
                    continue
                
                # 尝试将object映射到实体（Company, Campaign, Concept）
                object_label = None
                
                # 先尝试Company
                obj_company = session.run("""
                    MATCH (c:Company)
                    WHERE toLower(c.name) = toLower($obj)
                    RETURN c, 'Company' as label LIMIT 1
                """, obj=obj).single()
                
                if obj_company:
                    object_label = 'Company'
                else:
                    # 尝试Campaign（如果object包含活动关键词）
                    campaign_keywords = ['campaign', '活动', 'event', 'promotion', '促销', '大促']
                    if any(kw in obj.lower() for kw in campaign_keywords):
                        # 创建Campaign节点
                        session.run("""
                            MERGE (c:Campaign {name: $name})
                            ON CREATE SET c.created_at = datetime()
                        """, name=obj)
                        object_label = 'Campaign'
                    else:
                        # 创建Concept节点（通用概念）
                        session.run("""
                            MERGE (c:Concept {name: $name})
                            ON CREATE SET c.created_at = datetime()
                        """, name=obj)
                        object_label = 'Concept'
                
                # 创建关系（使用SPO_REL关系，predicate作为属性）
                if object_label:
                    session.run(f"""
                        MATCH (c1:Company {{name: $subject}})
                        MATCH (c2:{object_label} {{name: $obj}})
                        MERGE (c1)-[r:SPO_REL]->(c2)
                        ON CREATE SET 
                            r.predicate = $predicate,
                            r.section_id = $section_id,
                            r.level2_code = $level2_code,
                            r.created_at = datetime()
                        ON MATCH SET
                            r.predicate = $predicate,
                            r.section_id = $section_id,
                            r.level2_code = $level2_code
                    """,
                        subject=subject,
                        obj=obj,
                        predicate=predicate,
                        section_id=section_id,
                        level2_code=level2_code
                    )
                    
                    self.stats['spo_relations_created'] += 1
    
    def _create_company_category_summary(self):
        """创建Company与CategoryL2的汇总关系"""
        with self.driver.session(database=self.database) as session:
            # 统计每个Company在每个CategoryL2中的出现次数（通过关系获取level2）
            result = session.run("""
                MATCH (c2:CategoryL2)-[:HAS_SECTION]->(s:Section)-[:MENTIONS_COMPANY]->(c:Company)
                WITH c, c2.code as level2_code, count(s) as mention_count,
                     collect(s.id)[0] as first_section_id
                MERGE (c)-[r:INVOLVED_IN_CATEGORY]->(c2)
                ON CREATE SET 
                    r.count = mention_count,
                    r.first_section_id = first_section_id,
                    r.created_at = datetime()
                ON MATCH SET
                    r.count = mention_count
                RETURN count(r) as relations_created
            """)
            
            record = result.single()
            if record:
                self.stats['involved_in_category_relations'] = record['relations_created']
                self.logger.info(f"  ✅ 创建了 {record['relations_created']} 个INVOLVED_IN_CATEGORY关系")
    
    def _show_statistics(self):
        """显示统计信息"""
        self.logger.info("=" * 70)
        self.logger.info("📊 导入统计")
        self.logger.info("=" * 70)
        self.logger.info(f"  CategoryL1节点: {self.stats['category_l1_created']}")
        self.logger.info(f"  CategoryL2节点: {self.stats['category_l2_created']}")
        self.logger.info(f"  Section节点: {self.stats['sections_created']}")
        self.logger.info(f"  Company节点: {self.stats['companies_created']}")
        self.logger.info(f"  Brand节点: {self.stats['brands_created']}")
        self.logger.info(f"  CompanyType节点: {self.stats['company_types_created']}")
        self.logger.info(f"  SPO关系: {self.stats['spo_relations_created']}")
        self.logger.info(f"  INVOLVED_IN_CATEGORY关系: {self.stats['involved_in_category_relations']}")
        self.logger.info(f"  BELONGS_TO_BRAND关系: {self.stats['belongs_to_brand_relations']}")
        self.logger.info(f"  BELONGS_TO_TYPE关系: {self.stats['belongs_to_type_relations']}")
        
        # 查询Neo4j中的实际统计
        with self.driver.session(database=self.database) as session:
            result = session.run("""
                MATCH (n)
                RETURN labels(n)[0] as label, count(n) as count
                ORDER BY count DESC
            """)
            
            self.logger.info("📈 Neo4j节点统计:")
            self.logger.info("-" * 70)
            for record in result:
                self.logger.info(f"  {record['label']}: {record['count']} 个")
    
    def close(self):
        """关闭连接"""
        if self.driver:
            self.driver.close()


if __name__ == "__main__":
    import sys
    
    # 支持命令行参数
    uri = sys.argv[1] if len(sys.argv) > 1 else None
    
    writer = EnhancedKGWriter(uri=uri)
    
    try:
        writer.create_schema()
        writer.process_json_files()
    finally:
        writer.close()

