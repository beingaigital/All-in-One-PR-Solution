#!/usr/bin/env python3
"""
方案质量评估系统。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class QualityMetric(Enum):
    RELEVANCE = "relevance"
    INNOVATION = "innovation"
    FEASIBILITY = "feasibility"
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    PROFESSIONALISM = "professionalism"


@dataclass
class QualityScore:
    metric: str
    score: float
    weight: float
    explanation: str


@dataclass
class QualityAssessment:
    plan_id: str
    overall_score: float
    metric_scores: List[QualityScore]
    assessment_type: str
    assessor_id: Optional[str]
    timestamp: str
    comments: Optional[str]
    improvements: List[str]


class QualityEvaluator:
    """质量评估器。"""

    def __init__(self) -> None:
        self.metric_weights = {
            "relevance": 0.25,
            "innovation": 0.20,
            "feasibility": 0.20,
            "completeness": 0.15,
            "consistency": 0.10,
            "professionalism": 0.10,
        }

    def evaluate_plan(
        self,
        plan_id: str,
        plan_content: str,
        context: Dict[str, Any],
        assessment_type: str = "automatic",
    ) -> QualityAssessment:
        metric_scores = [
            self._evaluate_metric(metric.value, plan_content, context) for metric in QualityMetric
        ]
        overall_score = sum(score.score * score.weight for score in metric_scores)
        improvements = self._generate_improvements(metric_scores)
        return QualityAssessment(
            plan_id=plan_id,
            overall_score=overall_score,
            metric_scores=metric_scores,
            assessment_type=assessment_type,
            assessor_id=None,
            timestamp=datetime.now().isoformat(),
            comments=None,
            improvements=improvements,
        )

    def human_evaluate_plan(
        self,
        plan_id: str,
        metric_scores: Dict[str, float],
        overall_score: float,
        comments: Optional[str] = None,
        improvements: Optional[List[str]] = None,
        assessor_id: Optional[str] = None,
    ) -> QualityAssessment:
        quality_scores = [
            QualityScore(metric=metric, score=score, weight=self.metric_weights.get(metric, 0.1), explanation="人工评估")
            for metric, score in metric_scores.items()
        ]
        return QualityAssessment(
            plan_id=plan_id,
            overall_score=overall_score,
            metric_scores=quality_scores,
            assessment_type="human",
            assessor_id=assessor_id,
            timestamp=datetime.now().isoformat(),
            comments=comments,
            improvements=improvements or [],
        )

    def _evaluate_metric(self, metric: str, plan_content: str, context: Dict[str, Any]) -> QualityScore:
        weight = self.metric_weights.get(metric, 0.1)
        evaluators = {
            "relevance": self._evaluate_relevance,
            "innovation": self._evaluate_innovation,
            "feasibility": self._evaluate_feasibility,
            "completeness": self._evaluate_completeness,
            "consistency": self._evaluate_consistency,
            "professionalism": self._evaluate_professionalism,
        }
        score, explanation = evaluators.get(metric, self._unknown_metric)(plan_content, context)
        return QualityScore(metric=metric, score=score, weight=weight, explanation=explanation)

    def _unknown_metric(self, *_: Any) -> Tuple[float, str]:
        return 0.5, "未定义的指标"

    def _evaluate_relevance(self, plan_content: str, context: Dict[str, Any]) -> Tuple[float, str]:
        brand = context.get("brand", "")
        pr_goal = context.get("pr_goal", "")
        industry = context.get("industry", "")
        relevance_score = 0.5
        explanation_parts = []

        if brand and brand in plan_content:
            relevance_score += 0.2
            explanation_parts.append(f"方案提到了品牌 {brand}")
        else:
            explanation_parts.append(f"方案未明确提到品牌 {brand}")

        if pr_goal:
            goal_keywords = {
                "品牌认知": ["认知", "知名度", "曝光", "传播"],
                "用户增长": ["用户", "增长", "获客", "转化"],
                "危机公关": ["危机", "应对", "处理", "修复"],
            }
            keywords = goal_keywords.get(pr_goal, [])
            if any(kw in plan_content for kw in keywords):
                relevance_score += 0.2
                explanation_parts.append(f"方案与目标 '{pr_goal}' 相关")
            else:
                explanation_parts.append(f"方案与目标 '{pr_goal}' 相关性不足")

        if industry and industry in plan_content:
            relevance_score += 0.1
            explanation_parts.append("方案考虑了行业特点")

        score = min(relevance_score, 1.0)
        return score, "; ".join(explanation_parts)

    def _evaluate_innovation(self, plan_content: str, _: Dict[str, Any]) -> Tuple[float, str]:
        innovation_keywords = ["创新", "新颖", "独特", "突破", "差异化", "创意", "新玩法", "新模式", "新渠道"]
        innovation_count = sum(1 for kw in innovation_keywords if kw in plan_content)
        score = min(innovation_count * 0.15 + 0.3, 1.0)
        return score, f"方案包含 {innovation_count} 个创新相关关键词"

    def _evaluate_feasibility(self, plan_content: str, _: Dict[str, Any]) -> Tuple[float, str]:
        feasibility_indicators = ["步骤", "流程", "时间", "预算", "资源", "实施", "执行", "操作", "方法", "策略"]
        indicator_count = sum(1 for ind in feasibility_indicators if ind in plan_content)
        score = min(indicator_count * 0.1 + 0.4, 1.0)
        if "预算" in plan_content or "成本" in plan_content:
            score += 0.1
        if "时间" in plan_content or "周期" in plan_content:
            score += 0.1
        return min(score, 1.0), f"方案包含 {indicator_count} 个可行性指标"

    def _evaluate_completeness(self, plan_content: str, _: Dict[str, Any]) -> Tuple[float, str]:
        required_sections = ["目标", "策略", "渠道", "内容", "时间", "预算"]
        section_count = sum(1 for section in required_sections if section in plan_content)
        score = min(section_count / len(required_sections), 1.0)
        return score, f"方案包含 {section_count}/{len(required_sections)} 个必要部分"

    def _evaluate_consistency(self, plan_content: str, _: Dict[str, Any]) -> Tuple[float, str]:
        contradictions = [("保守", "激进"), ("低成本", "高预算"), ("短期", "长期")]
        contradiction_count = sum(1 for neg, pos in contradictions if neg in plan_content and pos in plan_content)
        if contradiction_count == 0:
            return 0.8, "方案内部一致性良好"
        score = max(0.5 - contradiction_count * 0.1, 0.3)
        return score, f"方案存在 {contradiction_count} 处可能的不一致"

    def _evaluate_professionalism(self, plan_content: str, _: Dict[str, Any]) -> Tuple[float, str]:
        professional_keywords = [
            "策略",
            "方案",
            "执行",
            "评估",
            "KPI",
            "ROI",
            "目标受众",
            "传播渠道",
            "内容营销",
            "品牌传播",
        ]
        keyword_count = sum(1 for kw in professional_keywords if kw in plan_content)
        score = min(keyword_count * 0.1 + 0.5, 1.0)
        if len(plan_content) > 500:
            score = min(score + 0.1, 1.0)
        return score, f"方案使用了 {keyword_count} 个专业术语"

    @staticmethod
    def _generate_improvements(metric_scores: List[QualityScore]) -> List[str]:
        improvements = []
        for score in metric_scores:
            if score.score >= 0.6:
                continue
            suggestions = {
                "relevance": "增强方案与品牌和目标的相关性",
                "innovation": "增加创新元素和差异化策略",
                "feasibility": "提供更具体的实施步骤和资源需求",
                "completeness": "补充缺失的方案组成部分",
                "consistency": "检查并修正方案中的不一致之处",
                "professionalism": "使用更多专业术语和行业标准",
            }
            improvements.append(suggestions.get(score.metric, "加强该指标表现"))
        return improvements

