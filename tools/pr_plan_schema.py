"""方案模板说明工具。"""

from __future__ import annotations

import json

from langchain_core.tools import tool


@tool
def pr_plan_schema() -> str:
    """
    描述：返回 PRClaw 支持的方案模板类型与输入字段说明。
    使用时机：在生成方案前，先确认输出类型和输入字段。
    输入：无。
    输出：JSON 字符串，包含 output_types 与 required_fields。
    """
    payload = {
        "output_types": {
            "A": "图文创意简报",
            "B": "视频脚本",
            "C": "整合活动方案",
            "D": "短视频脚本",
            "E": "小红书种草笔记",
            "F": "危机公关方案",
        },
        "required_fields": [
            "enterprise_name",
            "industry",
            "pr_cycle",
            "pr_budget",
            "pr_goal",
        ],
        "recommended_fields": [
            "enterprise_stage",
            "market_type",
            "innovation",
            "target_audience",
            "key_messages",
            "extra_requirements",
        ],
    }
    return json.dumps(payload, ensure_ascii=False)
