"""方案反馈采集工具（RLHF）。"""

from __future__ import annotations

import json
from datetime import datetime

from langchain_core.tools import tool

from utils.all_in_one_adapter import get_all_in_one_adapter


@tool
def pr_collect_feedback(
    plan_id: str,
    rating: float,
    comment: str = "",
    strategy_score: float = 0.0,
    creativity_score: float = 0.0,
    feasibility_score: float = 0.0,
) -> str:
    """
    描述：为已生成方案记录反馈，用于 RLHF 学习闭环。
    使用时机：当用户对某个 plan_id 的质量进行评价时。
    输入：plan_id、rating（必填），其余评分项和评论可选。
    输出：JSON 字符串，包含反馈写入结果。
    """
    adapter = get_all_in_one_adapter()

    kwargs = {
        "strategy_score": strategy_score,
        "creativity_score": creativity_score,
        "feasibility_score": feasibility_score,
    }

    result = adapter.collect_feedback(
        plan_id=plan_id,
        rating=rating,
        comment=comment,
        **kwargs,
    )

    payload = {
        "timestamp": datetime.now().isoformat(),
        "plan_id": plan_id,
        "rating": rating,
        "comment": comment,
        "result": result,
    }
    return json.dumps(payload, ensure_ascii=False)
