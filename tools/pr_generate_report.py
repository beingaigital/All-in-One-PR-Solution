"""公关传播报告生成工具。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

from langchain_core.tools import tool

from utils.all_in_one_adapter import get_all_in_one_adapter


@tool
def pr_generate_report(
    goal: str,
    audience: str,
    tone: str = "专业",
    length: str = "中篇",
    report_format: str = "markdown",
    timeframe: str = "",
    citation_pref: str = "需要来源标注",
    channels: str = "",
    industry: str = "",
    brand: str = "",
    extras: str = "",
    confirm_requirements: bool = True,
    dry_run: bool = False,
    use_graph_rag: bool = True,
) -> str:
    """
    描述：生成公关传播报告，可先进行需求确认，再输出结构化报告。
    使用时机：当需要整套报告交付（执行摘要、KPI、受众、渠道、排期、风险与复盘）时。
    输入：goal / audience（必填）；其余为选填。
    输出：JSON 字符串，包含状态、确认摘要或最终报告内容。
    """
    adapter = get_all_in_one_adapter()

    channel_list = [x.strip() for x in channels.replace("，", ",").split(",") if x.strip()]

    requirements: Dict[str, Any] = {
        "goal": goal,
        "audience": audience,
        "tone": tone,
        "length": length,
        "format": report_format,
        "timeframe": timeframe,
        "citation_pref": citation_pref,
        "channels": channel_list,
        "industry": industry,
        "brand": brand,
    }

    if extras.strip():
        requirements["extras"] = extras.strip()

    result = adapter.generate_report(
        requirements=requirements,
        confirm=bool(confirm_requirements),
        dry_run=bool(dry_run),
        use_graph=bool(use_graph_rag),
    )

    payload = {
        "timestamp": datetime.now().isoformat(),
        "requirements": requirements,
        "result": result,
    }
    return json.dumps(payload, ensure_ascii=False)
