#!/usr/bin/env python3
"""
合并后的统一公关传播智能体系统（v1.1）
基于 v1.1 RAG 系统提供知识查询、实体分析和方案生成功能
"""

import os
import json
import argparse
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
import yaml
from utils.path import get_config_path

# 加载环境变量（确保 .env 文件被读取）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(str(ENV_PATH), override=True)
except ImportError:
    # 如果没有 dotenv，手动读取 .env 文件
    if ENV_PATH.exists():
        with open(ENV_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

# 导入现有RAG系统组件（使用 v1.1 版本）
import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.querying.pipelines import EnhancedPRRAGSystemV11 as EnhancedPRRAGSystem
from core.common.pr_neo4j_env import *

# 导入实体提取器（使用 v1.1 系统的实现）
try:
    from core.processing.extractors.entity_extractor import EntityRelationshipExtractor
    ENTITY_EXTRACTOR_AVAILABLE = True
except ImportError as e:
    ENTITY_EXTRACTOR_AVAILABLE = False
    print(f"⚠️ 实体提取器不可用: {e}")

# 导入RLHF相关组件
try:
    from core.rlhf.pr_enhanced_rag_with_rlhf import EnhancedPRRAGWithRLHF
    from core.rlhf.data import BrandKnowledgeManager, FeedbackCollector
    from core.rlhf.policies import MethodologyRulesManager
    from core.rlhf.trainer import QualityEvaluator, RLHFTrainer, RewardModel
    RLHF_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ RLHF模块导入失败: {e}")
    RLHF_AVAILABLE = False

# 导入方案生成器（v1.1）
try:
    from core.generation import (
        PRPlanGenerator,
        llm_complete,
        A_GRAPHIC_BRIEF,
        B_VIDEO_SCRIPT,
        C_CAMPAIGN_PLAN,
        D_SHORTVIDEO_SCRIPT,
        E_XHS_NOTE,
        F_CRISIS_PLAN,
        PRReportGenerator,
    )
    PLAN_GENERATOR_AVAILABLE = True
except ImportError as e:
    PLAN_GENERATOR_AVAILABLE = False
    print(f"⚠️ 方案生成器不可用: {e}")

class UnifiedPRSystem:
    """统一的公关传播智能体系统"""
    
    def __init__(self, config_path: str = "config/unified_config.yaml", enable_rlhf: bool = True):
        """初始化统一系统"""
        self.config = self.load_config(config_path)
        self.rag_system = None
        self.plan_generator = None
        self.entity_extractor = None
        self.llm_config = self._normalize_llm_config(self.config.get("llm", {}) or {})
        rlhf_cfg = self.config.get("rlhf", {}) if isinstance(self.config.get("rlhf"), dict) else {}
        self.enable_rlhf = enable_rlhf and RLHF_AVAILABLE and bool(rlhf_cfg.get("enabled", True))
        self.rlhf_generation_enabled = bool(rlhf_cfg.get("use_for_generation", False))
        self.llm_provider = self.llm_config.get("provider") or os.getenv("LLM_PROVIDER")
        self._bootstrap_llm_runtime_env()
        
        # RLHF组件
        self.rlhf_system = None
        self.brand_manager = None
        self.rules_manager = None
        self.feedback_collector = None
        self.report_generator: Optional["PRReportGenerator"] = None
        
        # 初始化组件
        self._init_components()
    
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        else:
            # 创建默认配置
            return self.create_default_config(config_path)
    
    def create_default_config(self, config_path: str) -> Dict[str, Any]:
        """创建默认配置"""
        default_config = {
            'llm': {
                'provider': 'openai_compatible',
                'model': 'qwen3.5-plus',
                'max_tokens': 2048,
                'temperature': 0.6,
                'base_url': os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or "https://coding.dashscope.aliyuncs.com/v1",
                'api_key_env': "APIKEY",
            },
            'neo4j': {
                'uri': os.getenv('NEO4J_URI', 'neo4j://127.0.0.1:7687'),
                'user': os.getenv('NEO4J_USERNAME', 'neo4j'),
                'password': os.getenv('NEO4J_PASSWORD', 'bjtu1234'),
                'database': os.getenv('NEO4J_DATABASE', 'neo4j')
            },
            'vector_store': {
                'persist_dir': './vector_store/chroma_db',
                'collection_name': 'pr_unified'
            },
            'retrieval': {
                'top_k': 10,
                'max_context_chars': 16000
            },
            'paths': {
                'output_dir': './outputs',
                'data_dir': './data'
            },
            "rlhf": {
                "enabled": True,
                "use_for_generation": False,
            },
        }
        
        # 保存默认配置
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
        
        return default_config

    @staticmethod
    def _expand_env_token(value: Any) -> str:
        """展开 ${ENV} 风格占位符。"""
        raw = str(value or "").strip()
        if raw.startswith("${") and raw.endswith("}") and len(raw) > 3:
            env_key = raw[2:-1].strip()
            return os.getenv(env_key, "")
        return raw

    @staticmethod
    def _normalize_provider_name(provider: str) -> str:
        val = str(provider or "").strip().lower()
        if val in {"openai-compatible", "openai_compat", "compatible"}:
            return "openai_compatible"
        return val or "openai"

    @staticmethod
    def _looks_non_openai_model(model_name: str) -> bool:
        model = str(model_name or "").strip().lower()
        if not model:
            return False
        return not model.startswith(("gpt", "o1", "o3", "o4"))

    def _load_main_model_profile(self) -> Dict[str, Any]:
        """读取 config/model.yaml 的 main profile（若存在）。"""
        model_path = get_config_path("model.yaml")
        if not model_path.exists():
            return {}
        try:
            with open(model_path, "r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
            if isinstance(raw, dict):
                main_cfg = raw.get("main")
                if isinstance(main_cfg, dict):
                    return main_cfg
                # 兼容老写法：顶层就是 profile
                if raw.get("provider"):
                    return raw
        except Exception:
            return {}
        return {}

    def _normalize_llm_config(self, llm_cfg: Dict[str, Any]) -> Dict[str, Any]:
        """统一 LLM 配置来源，优先用户配置，缺失时回落 model.yaml。"""
        cfg = dict(llm_cfg or {})
        main_profile = self._load_main_model_profile()

        provider = self._normalize_provider_name(
            cfg.get("provider")
            or main_profile.get("provider")
            or os.getenv("LLM_PROVIDER")
            or "openai"
        )
        flash_model = str(
            cfg.get("flash_model")
            or cfg.get("model")
            or main_profile.get("model")
            or os.getenv("LLM_FLASH_MODEL")
            or "gpt-4o-mini"
        ).strip()
        thinking_model = str(
            cfg.get("thinking_model")
            or cfg.get("model")
            or main_profile.get("model")
            or os.getenv("LLM_THINKING_MODEL")
            or flash_model
        ).strip()

        # 典型误配修正：provider=openai 但模型明显非 OpenAI，则切到 openai_compatible。
        if provider == "openai" and (
            self._looks_non_openai_model(flash_model)
            or self._looks_non_openai_model(thinking_model)
        ):
            profile_provider = self._normalize_provider_name(main_profile.get("provider", ""))
            provider = profile_provider if profile_provider else "openai_compatible"

        cfg["provider"] = provider
        cfg["flash_model"] = flash_model
        cfg["thinking_model"] = thinking_model
        cfg["model"] = flash_model
        cfg.setdefault("api_key_env", str(main_profile.get("api_key_env", "")).strip())
        if "base_url" not in cfg and main_profile.get("base_url"):
            cfg["base_url"] = str(main_profile.get("base_url")).strip()
        return cfg

    def _resolve_llm_api_key(self) -> str:
        api_keys = self.llm_config.get("api_keys")
        provider = self._normalize_provider_name(self.llm_config.get("provider", "openai"))
        if isinstance(api_keys, dict):
            candidate = self._expand_env_token(api_keys.get(provider))
            if candidate:
                return candidate
            # openai_compatible 常见沿用 openai/qwen 键位
            if provider == "openai_compatible":
                for alias in ("openai", "qwen", "kimi", "deepseek", "google"):
                    candidate = self._expand_env_token(api_keys.get(alias))
                    if candidate:
                        return candidate
        env_key = str(self.llm_config.get("api_key_env") or "").strip()
        if env_key and os.getenv(env_key):
            return os.getenv(env_key, "")
        for key in (
            "LLM_API_KEY",
            "APIKEY",
            "OPENAI_API_KEY",
            "OPENAI_APIKEY",
            "QWEN_API_KEY",
            "QWEN_APIKEY",
            "KIMI_API_KEY",
            "KIMI_APIKEY",
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_APIKEY",
            "GOOGLE_API_KEY",
            "GOOGLE_APIKEY",
        ):
            if os.getenv(key):
                return os.getenv(key, "")
        return ""

    def _resolve_llm_base_url(self) -> str:
        provider = self._normalize_provider_name(self.llm_config.get("provider", "openai"))
        if self.llm_config.get("base_url"):
            return self._expand_env_token(self.llm_config.get("base_url"))

        base_urls = self.llm_config.get("base_urls")
        if isinstance(base_urls, dict):
            direct = self._expand_env_token(base_urls.get(provider))
            if direct:
                return direct
            if provider == "openai_compatible":
                for alias in ("openai_compatible", "qwen", "kimi", "deepseek", "google", "openai"):
                    direct = self._expand_env_token(base_urls.get(alias))
                    if direct:
                        return direct

        return (
            os.getenv("LLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or os.getenv("API_BASE_URL")
            or os.getenv("BASE_URL")
            or ""
        )

    def _bootstrap_llm_runtime_env(self) -> None:
        """把 unified_config 的 LLM 配置同步成运行时环境变量，统一下游组件行为。"""
        provider = self._normalize_provider_name(self.llm_config.get("provider", "openai"))
        flash_model = str(self.llm_config.get("flash_model") or "").strip()
        thinking_model = str(self.llm_config.get("thinking_model") or flash_model).strip()
        api_key = self._resolve_llm_api_key()
        base_url = self._resolve_llm_base_url()

        os.environ["LLM_PROVIDER"] = provider
        if flash_model:
            os.environ["LLM_FLASH_MODEL"] = flash_model
            os.environ["LLM_MODEL"] = flash_model
        if thinking_model:
            os.environ["LLM_THINKING_MODEL"] = thinking_model

        # 将硬编码模型统一映射到当前主模型，避免旧模块固定 gpt-* 造成 401/模型不存在
        if flash_model:
            os.environ.setdefault("LLM_FORCE_MODEL", flash_model)

        if api_key:
            os.environ["LLM_API_KEY"] = api_key
            os.environ.setdefault("APIKEY", api_key)
        if base_url:
            os.environ["LLM_BASE_URL"] = base_url
            os.environ.setdefault("OPENAI_BASE_URL", base_url)
    
    def _init_components(self):
        """初始化各个组件"""
        try:
            # 初始化增强RAG系统
            self.rag_system = EnhancedPRRAGSystem()
            print("✅ 增强RAG系统初始化成功")
            
            # 初始化实体提取器（使用 v1.1 系统）
            if ENTITY_EXTRACTOR_AVAILABLE:
                try:
                    self.entity_extractor = EntityRelationshipExtractor()
                    print("✅ 实体提取器初始化成功（v1.1）")
                except Exception as e:
                    print(f"⚠️ 实体提取器初始化失败: {e}")
                    self.entity_extractor = None
            else:
                self.entity_extractor = None
                print("ℹ️ 实体提取器不可用，已跳过")
            
            # 初始化方案生成器（使用 v1.1 RAG 系统）
            if PLAN_GENERATOR_AVAILABLE:
                try:
                    self.plan_generator = PRPlanGenerator(
                        rag_system=self.rag_system,
                        llm_config=self.llm_config
                    )
                    print("✅ 方案生成器初始化成功（v1.1）")
                except Exception as e:
                    print(f"⚠️ 方案生成器初始化失败: {e}")
                    self.plan_generator = None
            else:
                self.plan_generator = None
                print("ℹ️ 方案生成器不可用，已跳过")

            # 报告生成器（需求确认 + 方法论对齐）
            try:
                self.report_generator = PRReportGenerator(
                    rag_system=self.rag_system,
                    llm_provider=self.llm_provider,
                )
                print("✅ 报告生成器初始化成功（支持需求确认+方法论对齐）")
            except Exception as e:
                print(f"⚠️ 报告生成器初始化失败: {e}")
            
            # 初始化RLHF组件
            if self.enable_rlhf:
                try:
                    self.rlhf_system = EnhancedPRRAGWithRLHF()
                    self.brand_manager = BrandKnowledgeManager()
                    self.rules_manager = MethodologyRulesManager()
                    self.feedback_collector = FeedbackCollector()
                    mode = "启用" if self.rlhf_generation_enabled else "仅反馈学习"
                    print(f"✅ RLHF系统初始化成功（{mode}）")
                except Exception as e:
                    print(f"⚠️ RLHF系统初始化失败: {e}")
                    self.enable_rlhf = False
                    self.rlhf_generation_enabled = False
            
        except Exception as e:
            print(f"⚠️ 组件初始化警告: {e}")
    
    def query_knowledge(self, query: str, use_graph: bool = True) -> str:
        """知识查询功能（来自现有RAG系统）"""
        try:
            if use_graph:
                return self.rag_system.query(query, use_graph=True)
            else:
                return self.rag_system.query(query, use_graph=False)
        except Exception as e:
            return f"查询失败: {e}"
    
    def generate_pr_plan(self, enterprise_info: Dict[str, Any], output_types: List[str] = None) -> Dict[str, Any]:
        """生成公关传播方案（基于 v1.1 RAG 系统，支持RLHF）"""
        if output_types is None:
            output_types = ["A", "B", "C", "D", "E", "F"]
        
        try:
            # 若显式开启 RLHF 方案生成，则先走 RLHF。
            if self.enable_rlhf and self.rlhf_generation_enabled and self.rlhf_system:
                return self._generate_plan_with_rlhf(enterprise_info, output_types)
            return self._generate_plan_standard(enterprise_info, output_types)
            
        except Exception as e:
            return {"error": f"方案生成失败: {e}"}

    def _generate_plan_standard(self, enterprise_info: Dict[str, Any], output_types: List[str]) -> Dict[str, Any]:
        """标准方案生成链路（RAG + PRPlanGenerator）。"""
        if not self.plan_generator:
            return {"error": "方案生成器未初始化"}

        query = self._build_plan_query(enterprise_info)
        context = self.rag_system.query(query, use_graph=True) if self.rag_system else None
        return self.plan_generator.generate_plan(
            enterprise_info=enterprise_info,
            output_types=output_types,
            context=context,
        )

    def confirm_report_requirements(self, requirements: Dict[str, Any]) -> Dict[str, Any]:
        """生成报告前的需求确认摘要。"""
        if not self.report_generator:
            return {"error": "报告生成器未初始化"}
        return self.report_generator.confirm_requirements(requirements)

    def generate_report(self, requirements: Dict[str, Any], confirm: bool = False, dry_run: bool = False) -> Dict[str, Any]:
        """生成公关传播报告，需先确认需求。"""
        if not self.report_generator:
            return {"error": "报告生成器未初始化"}
        if not confirm:
            return self.confirm_report_requirements(requirements)
        return self.report_generator.generate_report(requirements, dry_run=dry_run)
    
    def _build_plan_query(self, enterprise_info: Dict[str, Any]) -> str:
        """构建方案生成查询"""
        parts = []
        if enterprise_info.get('enterprise_stage'):
            parts.append(enterprise_info['enterprise_stage'])
        if enterprise_info.get('industry'):
            parts.append(enterprise_info['industry'])
        if enterprise_info.get('market_type'):
            parts.append(enterprise_info['market_type'])
        if enterprise_info.get('pr_goal'):
            parts.append(f"目标:{enterprise_info['pr_goal']}")
        if enterprise_info.get('innovation'):
            parts.append(f"创新:{enterprise_info['innovation']}")
        
        return " ".join(parts) if parts else "公关传播策略和案例"
    
    def _generate_plan_with_rlhf(self, enterprise_info: Dict[str, Any], output_types: List[str]) -> Dict[str, Any]:
        """使用RLHF生成方案"""
        try:
            # 使用增强的RAG系统生成方案
            result = self.rlhf_system.generate_plan_with_feedback(enterprise_info, output_types)
            
            # 提取方案内容，返回标准格式 {plan_type: content}
            if isinstance(result, dict) and 'results' in result:
                plans = {}
                for plan_type, plan_data in result['results'].items():
                    if isinstance(plan_data, dict):
                        plans[plan_type] = plan_data.get('content', '')
                    else:
                        plans[plan_type] = str(plan_data)
                
                # 如果只需要方案内容，直接返回 plans
                # 如果需要保留元数据，可以返回包含 plan_results 的字典
                return plans
            else:
                # 如果格式不对，回退到标准方法
                return self._generate_plan_standard(enterprise_info, output_types)
        except Exception as e:
            print(f"RLHF方案生成失败: {e}")
            # 回退到原始方法
            return self._generate_plan_standard(enterprise_info, output_types)
    
    def analyze_entities(self, text: str) -> Dict[str, Any]:
        """实体分析功能"""
        if not self.entity_extractor:
            return {
                "error": "实体提取器不可用",
                "message": "实体提取器未初始化，实体分析功能已禁用"
            }
        
        try:
            entities = self.entity_extractor.extract_entities(text)
            relationships = self.entity_extractor.extract_relationships(text)
            
            return {
                "entities": entities,
                "relationships": relationships,
                "analysis_summary": f"识别到 {len(entities)} 个实体和 {len(relationships)} 个关系"
            }
        except Exception as e:
            return {"error": f"实体分析失败: {e}"}
    
    def unified_query(self, query: str, mode: str = "auto") -> Dict[str, Any]:
        """统一查询接口"""
        try:
            # 自动判断查询类型
            if mode == "auto":
                if any(keyword in query for keyword in ["方案", "策划", "计划", "生成"]):
                    mode = "plan_generation"
                elif any(keyword in query for keyword in ["实体", "关系", "分析"]):
                    mode = "entity_analysis"
                else:
                    mode = "knowledge_query"
            
            result = {
                "query": query,
                "mode": mode,
                "timestamp": datetime.now().isoformat(),
                "result": None
            }
            
            if mode == "knowledge_query":
                result["result"] = self.query_knowledge(query)
            elif mode == "entity_analysis":
                result["result"] = self.analyze_entities(query)
            elif mode == "plan_generation":
                # 这里需要解析查询中的企业信息
                enterprise_info = self._parse_enterprise_info(query)
                result["result"] = self.generate_pr_plan(enterprise_info)
            
            return result
            
        except Exception as e:
            return {
                "query": query,
                "mode": mode,
                "error": f"统一查询失败: {e}",
                "timestamp": datetime.now().isoformat()
            }
    
    def _parse_enterprise_info(self, query: str) -> Dict[str, Any]:
        """从查询中解析企业信息"""
        # 简单的解析逻辑，实际应用中可以使用更复杂的NLP
        enterprise_info = {
            "enterprise_name": "示例企业",
            "enterprise_stage": "中小微企业",
            "industry": "科技",
            "market_type": "ToC",
            "pr_goal": "品牌认知",
            "pr_cycle": "3个月",
            "pr_budget": "100万",
            "innovation": "适度创新"
        }
        
        # 尝试从查询中提取信息
        if "初创" in query:
            enterprise_info["enterprise_stage"] = "初创企业"
        elif "大型" in query:
            enterprise_info["enterprise_stage"] = "大型国企央企"
        
        if "ToB" in query:
            enterprise_info["market_type"] = "ToB"
        elif "ToG" in query:
            enterprise_info["market_type"] = "ToG"
        
        return enterprise_info
    
    def collect_feedback(self, plan_id: str, rating: float, comment: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """收集方案反馈"""
        if not self.enable_rlhf or not self.feedback_collector:
            return {"error": "RLHF功能未启用"}

        categories = kwargs.get("categories")
        if not isinstance(categories, dict):
            categories = {}

        for key in ("strategy_score", "creativity_score", "feasibility_score"):
            if key in kwargs:
                value = kwargs.get(key)
                if value is not None:
                    categories[key] = value

        metadata = kwargs.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        suggestions = kwargs.get("suggestions")
        if not isinstance(suggestions, list):
            suggestions = []

        return self.feedback_collector.collect_feedback(
            plan_id=plan_id,
            feedback_type='rating',
            rating=rating,
            comment=comment,
            categories=categories,
            suggestions=suggestions,
            user_id=kwargs.get("user_id"),
            metadata=metadata,
            knowledge_sources=kwargs.get("knowledge_sources"),
            plan_type=kwargs.get("plan_type"),
        )
    
    def get_feedback_analysis(self, plan_id: Optional[str] = None) -> Dict[str, Any]:
        """获取反馈分析"""
        if not self.enable_rlhf or not self.feedback_collector:
            return {"error": "RLHF功能未启用"}
        
        return self.feedback_collector.analyze_feedback(plan_id=plan_id)
    
    def get_learning_progress(self) -> Dict[str, Any]:
        """获取学习进度"""
        if not self.enable_rlhf or not self.rlhf_system:
            return {"error": "RLHF功能未启用"}
        
        return self.rlhf_system.get_learning_progress()
    
    def import_brand_knowledge(self, file_path: str, format: str = 'json') -> Dict[str, Any]:
        """导入品牌知识"""
        if not self.enable_rlhf or not self.brand_manager:
            return {"error": "RLHF功能未启用"}
        
        if format == 'json':
            return self.brand_manager.import_brands_from_json(file_path)
        elif format == 'csv':
            return self.brand_manager.import_brands_from_csv(file_path)
        elif format == 'excel':
            return self.brand_manager.import_brands_from_excel(file_path)
        else:
            return {"error": f"不支持的格式: {format}"}
    
    def import_methodology_rules(self, file_path: str) -> Dict[str, Any]:
        """导入方法论规则"""
        if not self.enable_rlhf or not self.rules_manager:
            return {"error": "RLHF功能未启用"}
        
        return self.rules_manager.import_rules_from_json(file_path)
    
    def close(self):
        """关闭系统"""
        # v1.1 系统不需要显式关闭连接
        print("✅ 系统已关闭")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="统一公关传播智能体系统")
    parser.add_argument("--mode", choices=["query", "generate", "analyze"], default="query", help="运行模式")
    parser.add_argument("--query", type=str, help="查询内容")
    parser.add_argument("--config", type=str, default="config/unified_config.yaml", help="配置文件路径")
    
    args = parser.parse_args()
    
    print("🤖 统一公关传播智能体系统")
    print("=" * 50)
    
    # 初始化系统
    system = UnifiedPRSystem(args.config)
    
    try:
        if args.mode == "query":
            if args.query:
                print(f"🔍 执行知识查询: {args.query}")
                result = system.unified_query(args.query, "knowledge_query")
                print(f"📝 查询结果:\n{result['result']}")
            else:
                print("❌ 查询模式需要提供 --query 参数")
                print("示例: python unified_pr_system.py --mode query --query '小米汽车如何做好用户运营？'")
        
        elif args.mode == "generate":
            print("📋 生成公关传播方案")
            enterprise_info = {
                "enterprise_name": "小米汽车",
                "enterprise_stage": "大型企业",
                "industry": "汽车",
                "market_type": "ToC",
                "pr_goal": "品牌认知",
                "pr_cycle": "6个月",
                "pr_budget": "500万",
                "innovation": "适度创新"
            }
            result = system.generate_pr_plan(enterprise_info, ["A", "B", "C"])
            print("📄 生成的方案:")
            
            # 处理返回结果
            if isinstance(result, dict):
                # 检查是否是错误信息
                if "error" in result:
                    print(f"❌ 错误: {result['error']}")
                else:
                    # 标准格式：{plan_type: content} 字典
                    for plan_type, content in result.items():
                        if isinstance(plan_type, str):
                            # 确保 content 是字符串
                            content_str = str(content) if not isinstance(content, str) else content
                            # 安全地截取前500个字符
                            preview = content_str[:500] if len(content_str) > 500 else content_str
                            print(f"\n{plan_type} 方案:\n{preview}...")
                        else:
                            print(f"\n方案类型: {plan_type}, 内容: {str(content)[:500]}...")
            else:
                print(f"⚠️ 意外的返回格式: {type(result)}")
                print(f"内容: {str(result)[:500]}...")
        
        elif args.mode == "analyze":
            if args.query:
                print(f"🔬 执行实体分析: {args.query}")
                result = system.unified_query(args.query, "entity_analysis")
                print(f"📊 分析结果:\n{result['result']}")
            else:
                print("❌ 分析模式需要提供 --query 参数")
                print("示例: python unified_pr_system.py --mode analyze --query '分析这个品牌案例'")
        
        else:
            print("📖 使用说明:")
            print("=" * 50)
            print("系统支持三种运行模式：")
            print()
            print("1. 知识查询模式（需要 --query）:")
            print("   python unified_pr_system.py --mode query --query '你的问题'")
            print()
            print("2. 方案生成模式（不需要 --query）:")
            print("   python unified_pr_system.py --mode generate")
            print()
            print("3. 实体分析模式（需要 --query）:")
            print("   python unified_pr_system.py --mode analyze --query '要分析的文本'")
            print()
            print("💡 提示: 使用 --help 查看详细参数说明")
    
    finally:
        system.close()

if __name__ == "__main__":
    main()
