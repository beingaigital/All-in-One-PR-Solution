#!/usr/bin/env python3
"""
Report generator with requirement confirmation and methodology grounding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.common.llm_provider import get_chat_llm
from core.knowledge.reference_loader import ReferenceSources

try:
    from core.querying.pipelines import EnhancedPRRAGSystemV11
except Exception:  # pragma: no cover
    EnhancedPRRAGSystemV11 = None


@dataclass
class ReportRequirements:
    goal: str = ""
    audience: str = ""
    tone: str = ""
    length: str = ""
    format: str = ""
    timeframe: str = ""
    citation_pref: str = ""
    channels: List[str] = field(default_factory=list)
    industry: Optional[str] = None
    brand: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReportRequirements":
        return cls(
            goal=data.get("goal", "") or data.get("pr_goal", ""),
            audience=data.get("audience", ""),
            tone=data.get("tone", ""),
            length=data.get("length", ""),
            format=data.get("format", ""),
            timeframe=data.get("timeframe", ""),
            citation_pref=data.get("citation_pref", ""),
            channels=data.get("channels", []) or [],
            industry=data.get("industry"),
            brand=data.get("brand") or data.get("enterprise_name"),
            extras={k: v for k, v in data.items() if k not in {
                "goal", "pr_goal", "audience", "tone", "length", "format",
                "timeframe", "citation_pref", "channels", "industry", "brand", "enterprise_name"
            }},
        )

    def summary(self) -> str:
        return (
            f"- 目标: {self.goal or '未提供'}\n"
            f"- 受众: {self.audience or '未提供'}\n"
            f"- 语气: {self.tone or '未提供'}\n"
            f"- 篇幅: {self.length or '未提供'}\n"
            f"- 格式: {self.format or '未提供'}\n"
            f"- 时间/时效: {self.timeframe or '未提供'}\n"
            f"- 引用偏好: {self.citation_pref or '未提供'}\n"
            f"- 渠道: {', '.join(self.channels) if self.channels else '未提供'}\n"
            f"- 行业: {self.industry or '未提供'}; 品牌: {self.brand or '未提供'}"
        )


class PRReportGenerator:
    """Report generator that confirms requirements and grounds outputs on methodology."""

    def __init__(
        self,
        rag_system: Optional[Any] = None,
        llm: Optional[object] = None,
        reference_sources: Optional[ReferenceSources] = None,
        llm_provider: Optional[str] = None,
    ) -> None:
        self.reference_sources = reference_sources or ReferenceSources()
        # 报告生成使用 thinking 档模型
        self.llm = llm or get_chat_llm(
            temperature=0.3,
            max_tokens=3200,
            provider=llm_provider,
            tier="thinking",
        )
        if rag_system is not None:
            self.rag_system = rag_system
        elif EnhancedPRRAGSystemV11 is not None:
            try:
                self.rag_system = EnhancedPRRAGSystemV11()
            except Exception:
                self.rag_system = None
        else:
            self.rag_system = None

    # ------------------------
    # Requirement confirmation
    # ------------------------
    def confirm_requirements(self, raw_requirements: Dict[str, Any]) -> Dict[str, Any]:
        req = ReportRequirements.from_dict(raw_requirements)
        return {
            "status": "pending_confirmation",
            "message": "请确认/修改以下报告需求后再生成：",
            "summary": req.summary(),
            "normalized": req.__dict__,
        }

    # ------------------------
    # Report generation
    # ------------------------
    def generate_report(
        self,
        confirmed_requirements: Dict[str, Any],
        dry_run: bool = False,
        use_graph: bool = True,
    ) -> Dict[str, Any]:
        req = ReportRequirements.from_dict(confirmed_requirements)
        methodology = self.reference_sources.methodology_text()
        methodology_hint = methodology[:1200] if methodology else ""

        # Build retrieval question from requirements
        retrieval_question = (
            f"{req.industry or ''} {req.brand or ''} {req.goal or ''} 渠道: {', '.join(req.channels)} "
            f"受众: {req.audience} 语气: {req.tone}"
        ).strip()

        context_blocks: List[str] = []
        citations: List[str] = []

        if self.rag_system and not dry_run:
            try:
                rag_context = self.rag_system.query(retrieval_question, use_graph=use_graph)
                context_blocks.append(rag_context)
                citations.append("rag_context")
            except Exception as exc:
                context_blocks.append(f"[RAG 查询失败 fallback] {exc}")
        else:
            context_blocks.append("RAG disabled (dry_run=True)，使用本地方法论+需求生成。")

        # Combine prompts
        prompt = (
            "你是一名公关传播方案专家，请基于需求与方法论生成报告。\n"
            f"需求：\n{req.summary()}\n\n"
            "方法论提示（来自《公关营销传播方法论》）：\n"
            f"{methodology_hint}\n\n"
            "检索上下文：\n"
            "\n".join(context_blocks)
            + "\n\n请输出结构化报告，包含：执行摘要、目标与KPI、受众洞察、核心信息与话术、渠道与内容策略、节奏与排期、风险与应对、测量与复盘。"
        )

        try:
            completion = self.llm.invoke(prompt)
            report_text = completion.content if hasattr(completion, "content") else str(completion)
        except Exception:
            report_text = (
                "【离线生成】\n"
                f"需求确认：\n{req.summary()}\n\n"
                f"方法论片段：\n{methodology_hint[:400]}\n\n"
                "报告草案：\n- 执行摘要：待完善\n- 渠道策略：结合渠道/目标表建议\n- 风险：保持信息一致，引用来源标注。"
            )

        return {
            "status": "generated",
            "report": report_text,
            "requirements": req.__dict__,
            "citations": citations + (["methodology"] if methodology_hint else []),
            "metadata": self.reference_sources.to_metadata(),
        }


__all__ = ["PRReportGenerator", "ReportRequirements"]
