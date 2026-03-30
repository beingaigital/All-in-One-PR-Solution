"""
方案生成执行器。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.generation.postprocessors import format_plan_results
from core.generation.templates import PLAN_TEMPLATES, get_template

from .llm_executor import LLMExecutor


class PRPlanGenerator:
    """公关传播方案生成器（基于 v1.1 RAG 系统）。"""

    def __init__(self, rag_system=None, llm_config: Optional[Dict[str, Any]] = None) -> None:
        self.rag_system = rag_system
        base_config = llm_config or {}
        self.llm_config = {
            "provider": base_config.get("provider", "openai"),
            "model": base_config.get("model")  # 兼容旧字段
                     or base_config.get("flash_model")
                     or "gpt-4o-mini",
            "max_tokens": base_config.get("max_tokens", 2048),
            "temperature": base_config.get("temperature", 0.6),
        }
        self._executor = LLMExecutor(
            provider=self.llm_config["provider"],
            model=self.llm_config["model"],
            max_tokens=self.llm_config["max_tokens"],
            temperature=self.llm_config["temperature"],
        )

    def generate_plan(
        self,
        enterprise_info: Dict[str, Any],
        output_types: Optional[List[str]] = None,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """生成多种类型的方案。"""
        output_types = output_types or list(PLAN_TEMPLATES.keys())

        enriched_context = context or self._fetch_context(enterprise_info)
        if not enriched_context:
            enriched_context = "基于行业最佳实践和案例经验"

        vars_text = json.dumps(enterprise_info, ensure_ascii=False)

        results: Dict[str, Any] = {}
        for plan_type in output_types:
            template = get_template(plan_type)
            if not template:
                continue
            prompt = template.format(context=enriched_context, vars=vars_text)
            results[plan_type] = self._executor.complete(prompt)

        return format_plan_results(results)

    def _fetch_context(self, enterprise_info: Dict[str, Any]) -> Optional[str]:
        """根据企业信息构建检索问题并调用 RAG。"""
        if not self.rag_system:
            return None
        query = self._build_query(enterprise_info)
        return self.rag_system.query(query, use_graph=True)

    @staticmethod
    def _build_query(enterprise_info: Dict[str, Any]) -> str:
        """构建查询语句。"""
        parts = []
        if enterprise_info.get("enterprise_stage"):
            parts.append(enterprise_info["enterprise_stage"])
        if enterprise_info.get("industry"):
            parts.append(enterprise_info["industry"])
        if enterprise_info.get("market_type"):
            parts.append(enterprise_info["market_type"])
        if enterprise_info.get("pr_goal"):
            parts.append(f"目标:{enterprise_info['pr_goal']}")
        if enterprise_info.get("innovation"):
            parts.append(f"创新:{enterprise_info['innovation']}")
        return " ".join(parts) if parts else "公关传播策略"
